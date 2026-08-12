#!/usr/bin/env python3
"""Phase 1 exit criterion (PLAN.md §9): forced-failure drills for
ops/runner.py. Each drill induces one specific failure mode against the real
pinned binary and asserts monitor_game() lands it in the correct terminal
status with artifacts attributed -- not a mocked classifier, the actual
process supervision path.

Drills, per PLAN.md §9 Phase 1 exit ("induced Lua error, kill -9, hang"):

1. lua_error: a hand-modified rc breaks qw's own ready() hook so every tick
   throws. crawl's clua catches this internally (mprf(MSGCH_ERROR, "Lua
   error: ...")) rather than crashing the process, so the game does NOT
   reach a clean EOF -- it goes stuck-and-erroring, which is exactly the
   ops/run-canary.py-established "check error patterns before concluding
   hang" path (docs/JOURNAL.md 2026-08-12 bug #3) that this drill exercises
   directly.
2. crashed (kill -9): simulates an external actor (OOM killer, preemption,
   an operator) killing the process out from under the harness -- not a
   harness-initiated kill. monitor_game must distinguish this from every
   other "process just disappeared" case via the child's signalstatus, with
   no logfile row.
3. hang: AUTO_START forced back off after rc-gen's template forces it on,
   so qw never acts post-chargen and the pty genuinely stops producing
   output -- the real progress-based hang path, not a simulated one.

Usage: runner-drills-test.py
Exit 0 and prints "PASS" on success; exit 1 with the failure(s) on failure.
"""
import pathlib
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
import combos  # noqa: E402
import runner  # noqa: E402
import importlib.util

_spec = importlib.util.spec_from_file_location("rc_gen", str(ROOT / "ops/rc-gen.py"))
rc_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc_gen)

# A fixed, cheap combo -- these drills care about harness behavior, not
# about the character actually doing anything interesting.
DRILL_CHAR_SEED = 999
DRILL_GAME_SEED = 5000


def _materialize(run_id, workdir, extra_rc_lines=None):
    manifest, digest = combos.load_manifest()
    row = rc_gen.build_manifest_row(run_id, DRILL_CHAR_SEED, DRILL_GAME_SEED, manifest, digest)
    layout = rc_gen.write_run_dir(row, workdir, turn_budget=0)
    if extra_rc_lines:
        with open(layout["rc_path"], "a") as f:
            f.write("\n" + "\n".join(extra_rc_lines) + "\n")
    logfile_path = layout["save_dir"] / "saves" / "logfile-seeded"
    cmd = [str(runner.CRAWL_BIN), "-rcdir", str(runner.QW_DIR)] + [str(a) for a in layout["clo_args"]]
    return cmd, logfile_path


def drill_lua_error():
    with tempfile.TemporaryDirectory(prefix="dcss-drill-luaerror-") as tmp:
        workdir = pathlib.Path(tmp)
        # Breaks qw's own ready() so every tick errors -- caught internally
        # by clua (non-fatal to the process), not a crash.
        cmd, logfile_path = _materialize("drill-luaerror", workdir, extra_rc_lines=[
            "{",
            "local orig_ready = ready",
            "function ready()",
            '    error("HARNESS_INDUCED_LUA_ERROR")',
            "end",
            "}",
        ])
        result = runner.monitor_game(cmd, workdir, logfile_path, run_id="drill-luaerror",
                                      wall_cap_secs=60, hang_secs=15, welcome_timeout_secs=30)
        ok = result["status"] == "lua_error"
        detail = f"status={result['status']!r} detail={result['detail']!r}"
        return ok, detail


def drill_kill9():
    with tempfile.TemporaryDirectory(prefix="dcss-drill-kill9-") as tmp:
        workdir = pathlib.Path(tmp)
        cmd, logfile_path = _materialize("drill-kill9", workdir)

        killed = threading.Event()

        def _kill_after_spawn(child):
            def _do_kill():
                time.sleep(3)
                try:
                    child.kill(9)
                finally:
                    killed.set()
            threading.Thread(target=_do_kill, daemon=True).start()

        result = runner.monitor_game(cmd, workdir, logfile_path, run_id="drill-kill9",
                                      wall_cap_secs=60, hang_secs=45, welcome_timeout_secs=30,
                                      on_spawn=_kill_after_spawn)
        if not killed.wait(timeout=1):
            return False, "kill thread never fired -- drill didn't actually run"
        ok = result["status"] == "crashed"
        detail = f"status={result['status']!r} detail={result['detail']!r}"
        return ok, detail


def drill_hang():
    with tempfile.TemporaryDirectory(prefix="dcss-drill-hang-") as tmp:
        workdir = pathlib.Path(tmp)
        # Deliberately does NOT go through rc-gen.py's template: that always
        # `include`s qw.lua, and appending a later `: AUTO_START = false`
        # override doesn't stick -- tried it, qw kept playing regardless
        # (empirically confirmed; whatever qw reads AUTO_START from isn't a
        # plain last-write-wins Lua global by the time ready() first fires).
        # Skipping the qw.lua include entirely is simpler and unambiguous:
        # crawl's own `combo=` still drives non-interactive chargen (it's a
        # crawl-native rc option, not qw's), but with no ready() hook
        # defined at all, nothing ever sends another key after the initial
        # "Welcome," dismiss -- a real, not simulated, stuck pty.
        rc_path = workdir / "drill-hang.rc"
        rc_path.write_text("combo = MuHu\n")
        save_dir = workdir / "saves"
        morgue_dir = workdir / "morgue"
        save_dir.mkdir(exist_ok=True)
        morgue_dir.mkdir(exist_ok=True)
        logfile_path = save_dir / "saves" / "logfile-seeded"
        cmd = [str(runner.CRAWL_BIN), "-lua-max-memory", "128", "-rc", str(rc_path),
               "-rcdir", str(runner.QW_DIR), "-name", "drillhang", "-seed", str(DRILL_GAME_SEED),
               "-dir", str(save_dir), "-morgue", str(morgue_dir), "-no-player-bones"]
        result = runner.monitor_game(cmd, workdir, logfile_path, run_id="drill-hang",
                                      wall_cap_secs=60, hang_secs=8, welcome_timeout_secs=30)
        ok = result["status"] == "timeout_wall" and "hang" in result["detail"]
        detail = f"status={result['status']!r} detail={result['detail']!r}"
        return ok, detail


DRILLS = [
    ("lua_error", drill_lua_error),
    ("kill9->crashed", drill_kill9),
    ("hang->timeout_wall", drill_hang),
]


def main():
    if not runner.CRAWL_BIN.exists():
        print(f"runner-drills-test.py: {runner.CRAWL_BIN} not found; build it first", file=sys.stderr)
        sys.exit(1)

    failures = []
    for name, fn in DRILLS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"drill raised {type(e).__name__}: {e}"
        print(("ok  " if ok else "FAIL") + f" {name}: {detail}")
        if not ok:
            failures.append(f"{name}: {detail}")

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print(f"PASS: {len(DRILLS)}/{len(DRILLS)} forced-failure drills landed in the correct status")
    sys.exit(0)


if __name__ == "__main__":
    main()
