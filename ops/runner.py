#!/usr/bin/env python3
"""Phase 1 runner state machine (PLAN.md §6): launches one sampled character
via ops/rc-gen.py, supervises it, and classifies the outcome into exactly one
of the terminal statuses:

    won | died | quit_intentional | quit_stuck | lua_error | crashed |
    timeout_turns | timeout_wall | invalid_telemetry | harness_failure

Classification is built on ops/rc-gen.py + ops/combos.py (the sampler/launch
pieces, already tested) and three pieces of research done this session, not
guessed:

1. crawl's end-of-game xlog row ("logfile", distinct from the DGL_MILESTONES
   "milestones" file) lands at `<-dir>/saves/logfile-seeded` (the extra
   nested `saves/` and the `-seeded` qualifier are both real crawl behavior,
   not typos — see hiscores.cc/state.cc/initfile.cc; confirmed empirically
   against this repo's own pin). It's written synchronously (fopen "a" /
   write / fclose, hiscores.cc's logfile_new_entry) at the moment the game
   ends, before any post-game UI screens — so polling for the file's
   appearance is a reliable, race-free way to detect a natural end without
   needing to shepherd the process through "-more-"/dump screens to reach
   process EOF.
2. Its `ktyp=` field is the authoritative terminal-outcome signal:
   `winning` -> won; `quitting` -> a Ctrl-Q "yes" quit (qw's only
   self-initiated quit path is its own QUIT_TURNS stuck-detection, so this
   is classified quit_stuck, not quit_intentional -- see
   docs/decisions/006); `leaving` -> qw's "Escape" goal walking out the D:1
   stairs without the Orb, a deliberate non-stuck exit -> quit_intentional;
   anything else -> died (there is no single generic "died" ktyp value, it's
   whichever cause fired, e.g. `mon`/`pois`/`starvation`/...).
3. A process that never produced a row because it was killed (by us, by the
   kernel on a real crash, or by an external actor) writes nothing --
   logfile_new_entry is only reachable from ouch()'s terminal branch. So
   "no row" cases are split by *how* the process ended: terminated by a
   signal we didn't send -> crashed (covers both a real segfault and an
   external kill -9 -- both are "died via a signal the harness didn't
   issue, no valid terminal row", which is what "crashed" should mean here);
   otherwise check the captured pty text for a Lua error banner (non-fatal
   to the process, qw carries on broken -- usually surfaces as a hang
   afterward, not a clean EOF) -> lua_error; otherwise invalid_telemetry.

Turn-budget enforcement (timeout_turns) is deliberately split across two
processes instead of done entirely in Lua: campaign.rc.tmpl's harness hook
only *observes* the budget and prints an on-screen sentinel
(HARNESS_TIMEOUT_TURNS) -- it does NOT also send the Ctrl-Q "yes" quit from
inside clua. An earlier version tried that with crawl.process_keys and it
hung: the quit keys landed in the same in-process macro queue qw's own
ready() is concurrently feeding every tick, and the two interleaved
unpredictably (confirmed by hand -- the sentinel fired but the process never
progressed). runner.py instead watches the pty stream for the sentinel from
the outside and kills the process itself the moment it's seen -- the same
external channel a human or qw's own util/qw.exp types into, so it can't
race qw's internal queueing, and it doesn't need a clean in-game quit to
work: no row means no ambiguity about the outcome.

Hang detection (also timeout_wall, PLAN §6: "no save/logfile/message mtime
change for N minutes") is progress-based off the captured pty output (the
same activity signal ops/run-canary.py/ops/telemetry-test.py already use and
proved reliable), not wall-clock alone. Before concluding hang OR wall-cap,
the error-pattern check runs first -- the same fix ops/run-canary.py needed
(docs/JOURNAL.md 2026-08-12 bug #3): a crashed-and-frozen game looks
identical to a genuinely stuck one from the outside.

Write-ahead accounting (PLAN §6: "a write-ahead manifest row ... committed
*before* launch") is one file per run, not a shared log: `manifest.json` is
written into the run's own directory before the process is spawned, and
`result.json` after it terminates. Per-run isolation already gives every run
a unique directory (ops/rc-gen.py never reuses one), so this needs no
locking or shared-file contention across parallel workers, and a future
collector can reconcile by globbing `manifest.json` vs `result.json` --
a manifest with no matching result is exactly the "crashed with no final
row, never silently dropped" case §6 requires it to catch.

Library use: `run_game(row, workdir, ...)` (the full write-ahead + spawn +
supervise + classify + result.json pipeline) or the lower-level
`monitor_game(cmd, workdir, logfile_path, ...)` (spawn + supervise only --
what ops/runner-drills-test.py uses to inject failures into an already-
materialized, hand-modified rc).
CLI use: `runner.py --run-id ID --char-seed N --game-seed N --workdir DIR
[--turn-budget N] [--wall-cap-secs N] [--hang-secs N]`.
"""
import argparse
import json
import pathlib
import re
import sys
import time

import pexpect

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
import combos  # noqa: E402
import xlog  # noqa: E402
import importlib.util

_spec = importlib.util.spec_from_file_location("rc_gen", str(ROOT / "ops/rc-gen.py"))
rc_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc_gen)

CRAWL_BIN = ROOT / "vendor/crawl/crawl-ref/source/crawl"
QW_DIR = ROOT / "vendor/qw"

# data/throughput-report.json (50 mixed combos, 900s safety cap, 8 workers):
# median wall-clock to a natural end was 88s, but 23/50 (46%) never reached
# one and hit the 900s cap -- many combos are simply durable and won't
# die/quit on their own within any short window, which is exactly why PLAN
# §6 wants turn budgets as the primary control and wall-clock only as a
# circuit breaker. 1800s gives ~2x that cap as headroom for campaign runs
# that get an explicit --turn-budget (the real per-run control -- this
# session didn't measure turn counts, only wall-clock, so a recommended
# turn-budget number is still open, left to whoever builds the campaign
# driver). hang_secs=120 is well above rc-gen-test.py's finding that 8-way
# concurrency alone can push a single "Welcome," handshake past 40s (a
# threshold tuned only under an idle machine would misfire under real
# campaign concurrency).
DEFAULT_WALL_CAP_SECS = 1800
DEFAULT_HANG_SECS = 120
DEFAULT_WELCOME_TIMEOUT_SECS = 60

TIMEOUT_SENTINEL = b"HARNESS_TIMEOUT_TURNS"
LUA_ERROR_RE = re.compile(r"Lua error|LUA ERROR|traceback", re.IGNORECASE)
CRASH_RE = re.compile(
    r"Segmentation fault|core dumped|terminate called|CRASH|Assertion.*failed",
    re.IGNORECASE,
)

# ktyp values from kill-method-type.h / hiscores.cc's kill_method_names[],
# for the two non-death terminal cases that aren't "winning": qw's only
# self-initiated quit path is QUIT_TURNS stuck-detection (quit_stuck); the
# "Escape" goal walking out the D:1 stairs without the Orb writes ktyp=
# leaving, a deliberate non-stuck exit (quit_intentional). Every other ktyp
# is a real death cause (mon/pois/starvation/...); there is no single
# generic "died" value, so anything not in this map or "winning" is "died".
_KTYP_STATUS = {
    "winning": "won",
    "quitting": "quit_stuck",
    "leaving": "quit_intentional",
}


def _check_error_patterns(buf):
    text = buf.decode(errors="replace")
    m = LUA_ERROR_RE.search(text)
    if m:
        return {"status": "lua_error", "detail": f"matched {m.group(0)!r} in output"}
    m = CRASH_RE.search(text)
    if m:
        return {"status": "crashed", "detail": f"matched {m.group(0)!r} in output"}
    return None


def _classify_row(row_text):
    lines = [l for l in row_text.splitlines() if l.strip()]
    if not lines:
        return {"status": "invalid_telemetry", "detail": "logfile exists but is empty"}
    try:
        fields = xlog.parse_line(lines[-1])
    except Exception as e:
        return {"status": "invalid_telemetry", "detail": f"logfile row failed to parse: {e}"}
    ktyp = fields.get("ktyp")
    if ktyp is None:
        return {"status": "invalid_telemetry", "detail": f"logfile row missing ktyp: {fields}",
                "logfile_row": fields}
    status = _KTYP_STATUS.get(ktyp, "died")
    return {"status": status, "detail": f"ktyp={ktyp}", "logfile_row": fields}


def _classify_eof_no_row(buf, child):
    try:
        child.wait()
    except Exception:
        pass
    if getattr(child, "signalstatus", None) is not None:
        return {"status": "crashed",
                "detail": f"process terminated by signal {child.signalstatus} with no logfile row"}
    err = _check_error_patterns(buf)
    if err:
        return err
    return {"status": "invalid_telemetry",
            "detail": "process exited with no logfile row and no error pattern matched"}


def _kill(child):
    try:
        if child.isalive():
            child.terminate(force=True)
            child.wait()
    except Exception:
        pass


def monitor_game(cmd, workdir, logfile_path, *, run_id="run",
                  wall_cap_secs=DEFAULT_WALL_CAP_SECS, hang_secs=DEFAULT_HANG_SECS,
                  welcome_timeout_secs=DEFAULT_WELCOME_TIMEOUT_SECS, on_spawn=None):
    """Spawn `cmd` (already-materialized rc/dirs, see run_game) and
    supervise it to a terminal status. Does not touch write-ahead
    accounting -- that's run_game's job, since drills call this directly
    against hand-modified rc files that don't go through the normal
    sampler->rc-gen path."""
    result = {"run_id": run_id, "status": "unknown", "detail": "",
              "logfile_row": None, "wall_secs": None, "output_bytes": 0}
    start = time.time()

    try:
        child = pexpect.spawn(" ".join(str(c) for c in cmd), timeout=30,
                               dimensions=(50, 130), cwd=str(workdir))
    except Exception as e:
        result.update(status="harness_failure", detail=f"spawn failed: {e}",
                       wall_secs=time.time() - start)
        return result

    if on_spawn:
        try:
            on_spawn(child)
        except Exception:
            pass

    buf = bytearray()
    try:
        child.expect(r"Welcome,", timeout=welcome_timeout_secs)
        buf += child.before + child.after
        child.send("\r")
    except pexpect.TIMEOUT:
        result.update(status="harness_failure",
                       detail=f"no 'Welcome,' banner within {welcome_timeout_secs}s "
                              "(chargen stuck or crashed)")
        _kill(child)
        result["wall_secs"] = time.time() - start
        return result
    except pexpect.EOF:
        buf += child.before
        result.update(_classify_eof_no_row(buf, child))
        result["wall_secs"] = time.time() - start
        result["output_bytes"] = len(buf)
        return result

    deadline = start + wall_cap_secs
    last_activity = time.time()
    last_len = len(buf)
    sentinel_seen = False
    hang_grace_used = False

    while True:
        now = time.time()

        if logfile_path.exists():
            row_text = logfile_path.read_text()
            if row_text.strip():
                result.update(_classify_row(row_text))
                break

        if now >= deadline:
            result.update(_check_error_patterns(buf)
                           or {"status": "timeout_wall", "detail": f"wall cap {wall_cap_secs}s reached"})
            break

        try:
            chunk = child.read_nonblocking(size=65536, timeout=2)
            buf += chunk
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            if hang_grace_used:
                # Ctrl-S's save_game(true) (files.cc:2603) exits the
                # process after saving -- a graceful save "succeeding" this
                # completely is expected, not a distinct outcome. Without
                # this check the EOF below would misroute it to
                # invalid_telemetry (empirically hit while writing the hang
                # drill: no logfile row is written by a plain save, only by
                # ouch()/end_game() on death/quit/win).
                result.update(status="timeout_wall",
                               detail=f"no progress for {hang_secs}s (hang); "
                                      "graceful save exited the process")
            else:
                result.update(_classify_eof_no_row(buf, child))
            break

        if not sentinel_seen and TIMEOUT_SENTINEL in buf:
            sentinel_seen = True
            result.update(status="timeout_turns",
                           detail="harness turn-budget sentinel observed; terminating")
            break

        if len(buf) != last_len:
            last_activity = now
            last_len = len(buf)
        elif now - last_activity > hang_secs:
            err = _check_error_patterns(buf)
            if err:
                result.update(err)
                break
            if not hang_grace_used:
                # PLAN §6: on hang, attempt one graceful save before killing.
                # Ctrl-S is crawl's own save-game command (also what qw's
                # plan_save() sends), independent of qw's internal state --
                # works whether or not qw itself is the thing that's stuck.
                hang_grace_used = True
                try:
                    child.send("\x13")
                except Exception:
                    pass
                last_activity = now
                continue
            result.update(status="timeout_wall",
                           detail=f"no progress for {hang_secs}s (hang); graceful save attempted")
            break

    result["wall_secs"] = time.time() - start
    result["output_bytes"] = len(buf)
    _kill(child)
    if result.get("logfile_row") is None and logfile_path.exists():
        # Best-effort informational capture only -- does not override the
        # status decided above (see module docstring on the sentinel race).
        try:
            text = logfile_path.read_text().strip()
            if text:
                result["logfile_row"] = xlog.parse_line(text.splitlines()[-1])
        except Exception:
            pass
    return result


def run_game(row, workdir, *, turn_budget=0, wall_cap_secs=DEFAULT_WALL_CAP_SECS,
             hang_secs=DEFAULT_HANG_SECS, welcome_timeout_secs=DEFAULT_WELCOME_TIMEOUT_SECS,
             bugfix_lua_errors=True, bugfix_indefinite_transform=True):
    """Write-ahead manifest -> materialize rc -> spawn -> supervise ->
    classify -> result.json. This is the entry point a campaign driver
    uses; monitor_game() is the lower-level piece drills use directly.

    bugfix_lua_errors (default True) is docs/decisions/011's Phase 2 A/B
    flag, threaded straight through to rc_gen.write_run_dir and recorded in
    the manifest for provenance (PLAN §8: "every run records ... config ...
    hashes").

    bugfix_indefinite_transform (default True) is docs/decisions/012's
    Phase 2 A/B flag, same threading/provenance treatment."""
    # Resolve before use: rc_gen.write_run_dir also resolves, but the
    # manifest/result paths and crawl's cwd must agree with it no matter
    # what shape of path the caller handed us (see write_run_dir's docstring
    # for the pilot-contamination bug a relative workdir caused).
    workdir = pathlib.Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    manifest_row = {
        **row, "turn_budget": turn_budget, "wall_cap_secs": wall_cap_secs,
        "hang_secs": hang_secs, "bugfix_lua_errors": bugfix_lua_errors,
        "bugfix_indefinite_transform": bugfix_indefinite_transform,
        "started_at": time.time(),
    }
    (workdir / "manifest.json").write_text(json.dumps(manifest_row, default=str))

    try:
        layout = rc_gen.write_run_dir(row, workdir, turn_budget=turn_budget,
                                       bugfix_lua_errors=bugfix_lua_errors,
                                       bugfix_indefinite_transform=bugfix_indefinite_transform)
    except Exception as e:
        result = {"run_id": row["run_id"], "status": "harness_failure",
                   "detail": f"write_run_dir failed: {e}", "wall_secs": 0, "output_bytes": 0,
                   "logfile_row": None}
        (workdir / "result.json").write_text(json.dumps(result, default=str))
        return result

    logfile_path = layout["save_dir"] / "saves" / "logfile-seeded"
    cmd = [str(CRAWL_BIN), "-rcdir", str(QW_DIR)] + [str(a) for a in layout["clo_args"]]

    result = monitor_game(cmd, workdir, logfile_path, run_id=row["run_id"],
                           wall_cap_secs=wall_cap_secs, hang_secs=hang_secs,
                           welcome_timeout_secs=welcome_timeout_secs)
    (workdir / "result.json").write_text(json.dumps(result, default=str))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--char-seed", type=int, required=True)
    ap.add_argument("--game-seed", type=int, required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--turn-budget", type=int, default=0)
    ap.add_argument("--wall-cap-secs", type=int, default=DEFAULT_WALL_CAP_SECS)
    ap.add_argument("--hang-secs", type=int, default=DEFAULT_HANG_SECS)
    ap.add_argument("--disable-bugfix-lua-errors", action="store_true",
                     help="reproduce the original qw crashes (docs/decisions/011); "
                          "for the Phase 2 A/B experiment's control arm")
    ap.add_argument("--disable-bugfix-indefinite-transform", action="store_true",
                     help="reproduce the original qw indefinite-transform rest stall "
                          "(docs/decisions/012); for the Phase 2 A/B experiment's control arm")
    args = ap.parse_args()

    if not CRAWL_BIN.exists():
        print(f"runner.py: {CRAWL_BIN} not found; build it first", file=sys.stderr)
        sys.exit(1)

    manifest, digest = combos.load_manifest()
    row = rc_gen.build_manifest_row(args.run_id, args.char_seed, args.game_seed, manifest, digest)
    result = run_game(row, args.workdir, turn_budget=args.turn_budget,
                       wall_cap_secs=args.wall_cap_secs, hang_secs=args.hang_secs,
                       bugfix_lua_errors=not args.disable_bugfix_lua_errors,
                       bugfix_indefinite_transform=not args.disable_bugfix_indefinite_transform)
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["status"] in ("won", "died", "quit_intentional", "quit_stuck") else 1)


if __name__ == "__main__":
    main()
