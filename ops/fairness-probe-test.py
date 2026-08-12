#!/usr/bin/env python3
"""Phase 1 fairness-contract probe test (PLAN.md §7: "Phase 1 includes probe
tests: assert that unseen monsters ... are absent from everything the policy
layer can read").

PLAN §4.1 already claims this is true "by construction," citing
l-moninf.cc — this test exercises that claim live against the real pinned
binary instead of only trusting the source reading. Reading
`l-moninf.cc:mi_get_monster_at` (the `monster.get_monster_at(dx, dy)`
binding every policy's monster-awareness ultimately goes through) turned up
a stronger guarantee than expected: the coordinate isn't just checked for
current visibility (`you.see_cell(p)`, returns nil if false) — the
`COORDSHOW` macro wrapping the coordinate parse (`cluautil.h`) rejects any
offset beyond `ENV_SHOW_OFFSET` (`defines.h`: `LOS_MAX_RANGE`, i.e. the LOS
radius, 8 in the pinned source) with a hard Lua error before the visibility
check is even reached. So there is no queryable coordinate space beyond LOS
at all, which makes "assert nil beyond LOS" untestable as originally framed
(nothing to query) — this test instead asserts the two things that *are*
directly observable and jointly demonstrate the same fairness property:

1. **Hard bounds cutoff**: querying one cell just past the LOS radius
   (`get_monster_at(0, 9)`) raises a Lua error, not a silent nil — proving
   the boundary is enforced at the API layer, not left to caller discipline.
2. **Positive control**: within LOS range, real qw-driven play (not
   wizard mode, not scripted) does observe non-nil results at least once
   over the probe window — proving the query mechanism actually detects
   monsters when they're legitimately visible, so a passing bounds check
   isn't concealing an "always nil" wiring bug that would trivially satisfy
   a naive fairness test without ever exercising the real code path.

Item-identification fairness (`items.*`'s `fully_identified`/`ego`/etc.
fields, l-item.cc) is deliberately left source-verified-only, not
live-probed here — constructing a live repro needs a guaranteed-unidentified
item in a specific background's starting kit, which is more scenario
engineering than this non-gating probe warrants; see
docs/decisions/009-fairness-probe-scope.md.

Reuses the MiBe/seed=2 repro (ops/telemetry-test.py, docs/decisions/005) --
already known to produce real monster encounters within ~90s.

Debug output uses `crawl.stderr()` (l-crawl.cc), not `crawl.mpr()`: an
earlier version used `crawl.mpr()` for the one-shot bounds-check message and
it never once appeared in the captured pty output across several full runs,
even though a plain print of the same text worked fine in a minimal
non-qw rc -- most likely crawl's message-pane redraw (which batches/limits
what's actually flushed per input cycle) can drop a message that's
immediately followed by another `mpr()` call in the same `ready()` tick
(exactly this probe's structure: the bounds check is followed immediately
by the per-tick in-LOS scan's own message). `crawl.stderr()` writes
directly to the process's stderr, which pexpect's pty capture picks up the
same as stdout, without going through message-pane rendering at all --
switching to it fixed the missing-message issue immediately and reliably.

Usage: fairness-probe-test.py [--budget-secs N]
Exit 0 and prints "PASS" on success; exit 1 with the failure(s) on failure.
"""
import argparse
import pathlib
import re
import sys
import tempfile
import time

import pexpect

ROOT = pathlib.Path(__file__).resolve().parent.parent
CRAWL_BIN = ROOT / "vendor/crawl/crawl-ref/source/crawl"
QW_DIR = ROOT / "vendor/qw"

RC_TEXT = """\
include = qw.rc
include = qw.lua

: AUTO_START = true
: DELAYED = false
combo = MiBe

{
local harness_orig_ready = ready
local bounds_checked = false
local last_probe_turn = -1000
local probe_count = 0
local max_probes = 40

function ready()
    harness_orig_ready()

    if probe_count >= max_probes then
        return
    end
    local t = you.turns()
    if t - last_probe_turn < 5 then
        return
    end
    last_probe_turn = t
    probe_count = probe_count + 1

    if not bounds_checked then
        bounds_checked = true
        local ok, err = pcall(function() return monster.get_monster_at(0, 9) end)
        crawl.stderr("PROBE_BOUNDS ok=" .. tostring(ok) .. " err=" .. tostring(err))
    end

    local ok, inlos_or_err = pcall(function()
        local n = 0
        for dx = -8, 8 do
            for dy = -8, 8 do
                if monster.get_monster_at(dx, dy) then
                    n = n + 1
                end
            end
        end
        return n
    end)
    if ok then
        crawl.stderr("PROBE_INLOS_COUNT n=" .. inlos_or_err .. " turn=" .. t)
    else
        crawl.stderr("PROBE_ERROR " .. tostring(inlos_or_err))
    end
end
}
"""

BOUNDS_RE = re.compile(r"PROBE_BOUNDS ok=(true|false) err=(.*)")
INLOS_RE = re.compile(r"PROBE_INLOS_COUNT n=(\d+) turn=(\d+)")
ERROR_RE = re.compile(r"PROBE_ERROR (.*)")


def run_probe(budget_secs, workdir):
    (workdir / "test.rc").write_text(RC_TEXT)
    save_dir = workdir / "saves"
    morgue_dir = workdir / "morgue"
    save_dir.mkdir(exist_ok=True)
    morgue_dir.mkdir(exist_ok=True)

    cmd = (
        f"{CRAWL_BIN} -lua-max-memory 128 -rc {workdir / 'test.rc'} -rcdir {QW_DIR} "
        f"-name fairnessprobe -seed 2 -dir {save_dir} -morgue {morgue_dir} "
        f"-no-player-bones"
    )
    child = pexpect.spawn(cmd, timeout=30, dimensions=(50, 130), cwd=str(workdir))
    child.expect(r"Welcome,", timeout=20)
    # The bounds probe fires on the very first ready() tick, which can
    # happen before this function's own read loop starts -- without folding
    # child.before/after in here first, that first message is lost (missed
    # empirically: PROBE_INLOS_COUNT lines showed up fine on later ticks but
    # PROBE_BOUNDS never did, because it's a one-shot on tick 1).
    buf = bytearray(child.before + child.after)
    child.send("\r")

    deadline = time.time() + budget_secs
    last_len = 0
    last_activity = time.time()
    while time.time() < deadline:
        try:
            chunk = child.read_nonblocking(size=65536, timeout=2)
            buf += chunk
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            break
        if len(buf) != last_len:
            last_activity = time.time()
            last_len = len(buf)
        elif time.time() - last_activity > 15:
            break
    try:
        if child.isalive():
            child.terminate(force=True)
            child.wait()
    except Exception:
        pass
    return buf.decode(errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-secs", type=int, default=90)
    args = ap.parse_args()

    if not CRAWL_BIN.exists():
        print(f"fairness-probe-test.py: {CRAWL_BIN} not found; build it first", file=sys.stderr)
        sys.exit(1)

    failures = []
    with tempfile.TemporaryDirectory(prefix="dcss-fairnessprobe-") as tmp:
        text = run_probe(args.budget_secs, pathlib.Path(tmp))

    bounds_matches = BOUNDS_RE.findall(text)
    inlos_matches = [(int(n), int(t)) for n, t in INLOS_RE.findall(text)]
    error_matches = ERROR_RE.findall(text)

    if len(bounds_matches) != 1:
        failures.append(f"expected exactly 1 PROBE_BOUNDS line, got {len(bounds_matches)}")
    elif bounds_matches[0][0] != "false":
        failures.append(
            f"get_monster_at(0, 9) (1 cell beyond LOS radius 8) did not raise an error "
            f"(ok={bounds_matches[0][0]}) -- the API-level bounds cutoff this fairness "
            f"claim relies on may have changed")

    if error_matches:
        failures.append(f"in-bounds scan loop raised {len(error_matches)} unexpected error(s): "
                         f"{error_matches[:3]}")

    if not inlos_matches:
        failures.append("no PROBE_INLOS_COUNT lines captured at all -- probe hook never fired")
    elif not any(n > 0 for n, _ in inlos_matches):
        failures.append(
            f"{len(inlos_matches)} in-LOS probes ran but none ever saw a monster "
            f"(all n=0) -- positive control failed, can't confirm get_monster_at actually "
            f"detects monsters rather than always returning nil")

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    max_seen = max(n for n, _ in inlos_matches)
    print(f"PASS: bounds cutoff confirmed (get_monster_at 1 cell beyond LOS radius errors), "
          f"{len(inlos_matches)} in-LOS probes ran with zero errors, "
          f"max monsters-in-LOS observed in one probe = {max_seen}")
    sys.exit(0)


if __name__ == "__main__":
    main()
