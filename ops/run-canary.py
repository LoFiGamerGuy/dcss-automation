#!/usr/bin/env python3
"""Phase 0 canary runner (PLAN.md §9 Phase 0 exit criterion).

Launches the pinned crawl+qw pair for one forced combo, lets qw play for a
wall-clock budget (a stand-in for "N decisions" — the real progress-based
runner state machine with turn-count instrumentation is Phase 1 work, not
built yet), and classifies the result: protocol error (Lua error/traceback
in output), hang (no output activity before the budget), or ok (qw played
without crawl-side or qw-side errors, whether or not the character is still
alive when the budget expires — dying is a normal outcome, not a failure).

Usage: run-canary.py <combo> [--seed N] [--budget-secs N] [--name NAME]
"""
import argparse
import pathlib
import re
import subprocess
import sys
import tempfile
import time

import pexpect

ROOT = pathlib.Path(__file__).resolve().parent.parent
CRAWL_BIN = ROOT / "vendor/crawl/crawl-ref/source/crawl"
QW_DIR = ROOT / "vendor/qw"
RC_TMPL = ROOT / "ops/canary/canary.rc.tmpl"

ERROR_PATTERNS = re.compile(
    r"Lua error|LUA ERROR|traceback|Segmentation fault|core dumped|"
    r"terminate called|CRASH|Assertion.*failed",
    re.IGNORECASE,
)


def run_canary(combo, seed, budget_secs, name, workdir):
    rc_text = RC_TMPL.read_text().replace("__COMBO__", combo)
    wrapper_rc = workdir / "canary.rc"
    wrapper_rc.write_text(rc_text)

    save_dir = workdir / "saves"
    morgue_dir = workdir / "morgue"
    save_dir.mkdir(exist_ok=True)
    morgue_dir.mkdir(exist_ok=True)

    cmd = (
        f"{CRAWL_BIN} -lua-max-memory 128 -rc {wrapper_rc} -rcdir {QW_DIR} "
        f"-name {name} -seed {seed} -dir {save_dir} -morgue {morgue_dir} "
        f"-no-player-bones"
    )

    child = pexpect.spawn(cmd, timeout=30, dimensions=(50, 130), cwd=str(workdir))
    output = bytearray()
    result = {"combo": combo, "seed": seed, "status": "unknown", "detail": ""}

    try:
        child.expect(r"Welcome,", timeout=20)
        output += child.before + child.after
        # The initial game-start banner is followed by a --more-- prompt
        # that blocks all input (including qw's clua hooks) until
        # dismissed; qw's own reference automation (util/qw.exp) sends this
        # same "\r" for exactly this reason. AUTO_START=true in our rc
        # template means qw is already active, so (unlike qw.exp) we must
        # NOT also send Tab, which would toggle it back off.
        child.send("\r")
    except pexpect.TIMEOUT:
        result["status"] = "hang"
        result["detail"] = "no 'Welcome,' banner within 20s (chargen stuck or crashed)"
        _finish(child, output, result)
        return result
    except pexpect.EOF:
        output += child.before
        result.update(_classify(output, "process exited before chargen completed"))
        _finish(child, output, result)
        return result

    deadline = time.time() + budget_secs
    last_activity = time.time()
    last_len = len(output)
    while time.time() < deadline:
        try:
            chunk = child.read_nonblocking(size=65536, timeout=2)
            output += chunk
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            break
        if len(output) != last_len:
            last_activity = time.time()
            last_len = len(output)
        elif time.time() - last_activity > 15:
            # No new output for 15s has two distinct causes that look
            # identical from the outside: a genuine hang, or a Lua/crash
            # error that halted the game (which also stops producing
            # output). Check for the error pattern before concluding hang
            # — otherwise every protocol error gets misfiled as a hang.
            result.update(_classify(
                output, f"no output for 15s (budget had {deadline - time.time():.0f}s left)"
            ))
            _finish(child, output, result)
            return result

    result.update(_classify(
        output, f"ran {budget_secs}s with no error pattern, process alive at budget end", default_ok=True
    ))
    _finish(child, output, result)
    return result


def _classify(output, no_error_detail, default_ok=False):
    text = output.decode(errors="replace")
    m = ERROR_PATTERNS.search(text)
    if m:
        return {"status": "protocol_error", "detail": f"matched {m.group(0)!r} in output"}
    if default_ok:
        return {"status": "ok", "detail": no_error_detail}
    return {"status": "hang", "detail": no_error_detail}


def _finish(child, output, result):
    try:
        if child.isalive():
            child.terminate(force=True)
            child.wait()
    except Exception:
        pass
    result["output_bytes"] = len(output)
    result["_raw_log"] = output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("combo")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--budget-secs", type=int, default=90)
    ap.add_argument("--name", default="canary")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="dcss-canary-") as tmp:
        workdir = pathlib.Path(tmp)
        r = run_canary(args.combo, args.seed, args.budget_secs, args.name, workdir)
        log_path = ROOT / "logs" / f"canary-{args.combo}-{args.seed}.log"
        log_path.parent.mkdir(exist_ok=True)
        log_path.write_bytes(r.pop("_raw_log", b""))
        print(f"{r['combo']} seed={r['seed']}: {r['status']} — {r['detail']} (log: {log_path})")
        sys.exit(0 if r["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
