#!/usr/bin/env python3
"""Phase 0 telemetry acceptance test (PLAN.md §6 / §9 Phase 0 exit).

Runs one scripted qw game against the pinned+built crawl binary and asserts
*exact* expected records/fields in the DGL_MILESTONES xlog file, not just
"a file appeared". combo=MiBe seed=2 budget=120s is a **fixed, previously
verified repro**: at this exact vendor pin it deterministically produces a
begin milestone, several uniq kills, and a Sewer portal br.enter/br.exit
pair (see docs/decisions/005-telemetry-verification-and-death-milestone-correction.md
for how this was found and why "death" is deliberately NOT asserted here).

Usage: telemetry-test.py [--combo COMBO] [--seed N] [--budget-secs N]
Exit 0 and prints "PASS" on success; exit 1 with the failed assertion(s) on
failure.
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
RC_TMPL = ROOT / "ops/canary/canary.rc.tmpl"


def xlog_parse_line(line):
    """Mirror hiscores.cc's _xlog_split_fields/_xlog_unescape: fields are
    ':'-separated key=value pairs, and a literal ':' inside a value is
    escaped as '::'."""
    fields = {}
    parts = []
    start = 0
    i = 0
    n = len(line)
    while i < n:
        if line[i] == ":":
            if i + 1 < n and line[i + 1] == ":":
                i += 2
                continue
            parts.append(line[start:i])
            i += 1
            start = i
            continue
        i += 1
    parts.append(line[start:])
    for part in parts:
        if "=" not in part:
            continue
        key, _, val = part.partition("=")
        fields[key] = val.replace("::", ":")
    return fields


def run_game(combo, seed, budget_secs, workdir):
    rc_text = RC_TMPL.read_text().replace("__COMBO__", combo)
    (workdir / "test.rc").write_text(rc_text)
    save_dir = workdir / "saves"
    morgue_dir = workdir / "morgue"
    save_dir.mkdir(exist_ok=True)
    morgue_dir.mkdir(exist_ok=True)

    cmd = (
        f"{CRAWL_BIN} -lua-max-memory 128 -rc {workdir / 'test.rc'} -rcdir {QW_DIR} "
        f"-name telemetry -seed {seed} -dir {save_dir} -morgue {morgue_dir} "
        f"-no-player-bones"
    )
    child = pexpect.spawn(cmd, timeout=30, dimensions=(50, 130), cwd=str(workdir))
    child.expect(r"Welcome,", timeout=20)
    child.send("\r")

    buf = bytearray()
    deadline = time.time() + budget_secs
    last_len = 0
    last_activity = time.time()
    died = False
    while time.time() < deadline:
        try:
            chunk = child.read_nonblocking(size=65536, timeout=2)
            buf += chunk
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            break
        if b"You die..." in buf:
            died = True
        if len(buf) != last_len:
            last_activity = time.time()
            last_len = len(buf)
        elif time.time() - last_activity > 8:
            if died:
                child.send(" ")
                child.send("\r")
                time.sleep(1)
            else:
                break
    try:
        if child.isalive():
            child.terminate(force=True)
            child.wait()
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--combo", default="MiBe")
    ap.add_argument("--seed", type=int, default=2)
    ap.add_argument("--budget-secs", type=int, default=120)
    args = ap.parse_args()

    if not CRAWL_BIN.exists():
        print(f"telemetry-test.py: {CRAWL_BIN} not found; build it first", file=sys.stderr)
        sys.exit(1)

    failures = []

    with tempfile.TemporaryDirectory(prefix="dcss-telemetry-") as tmp:
        workdir = pathlib.Path(tmp)
        run_game(args.combo, args.seed, args.budget_secs, workdir)

        mfile = workdir / "saves" / "saves" / "milestones-seeded"
        if not mfile.exists():
            print(f"FAIL: milestones file never created ({mfile})")
            sys.exit(1)

        records = [xlog_parse_line(l) for l in mfile.read_text().splitlines() if l.strip()]
        types_seen = [r.get("type") for r in records]

        def find(type_):
            return [r for r in records if r.get("type") == type_]

        # 1. begin: written once, at game start, with an unmistakable message.
        begins = find("begin")
        if len(begins) != 1:
            failures.append(f"expected exactly 1 'begin' record, got {len(begins)}: {types_seen}")
        elif begins[0].get("milestone") != "began the quest for the Orb.":
            failures.append(f"'begin' record has wrong milestone text: {begins[0].get('milestone')!r}")

        # 2. uniq: at least one unique-monster kill, with required place fields.
        uniqs = find("uniq")
        if not uniqs:
            failures.append(f"expected at least 1 'uniq' record, got 0: {types_seen}")
        else:
            for r in uniqs:
                if not r.get("milestone", "").startswith("killed "):
                    failures.append(f"'uniq' record has unexpected milestone text: {r.get('milestone')!r}")
                if "place" not in r or "br" not in r:
                    failures.append(f"'uniq' record missing place/br fields: {r}")

        # 3. br.enter: entering a branch (this repro reliably hits the Sewer
        # portal). Must carry the origin place (oplace) it was entered from.
        br_enters = find("br.enter")
        if not br_enters:
            failures.append(f"expected at least 1 'br.enter' record, got 0: {types_seen}")
        else:
            r = br_enters[0]
            if "oplace" not in r:
                failures.append(f"'br.enter' record missing 'oplace' (origin level): {r}")
            if r.get("br") == r.get("oplace", "").split(":")[0]:
                failures.append(f"'br.enter' record's branch equals its own origin branch: {r}")

        # 4. death is a v1-plan misconception, not an assertion here: ouch.cc's
        # mark_milestone("death", ...) call is gated on `you.lives` (extra-life
        # game modes only) — verified by reading ouch.cc and empirically, by
        # running this exact scripted game to a real death twice and finding
        # no 'death' record either time. Standard permadeath is captured in
        # the final *logfile* row instead (ktyp/killer/dam/sc fields), which
        # ops/run-canary.py's protocol-error detection already exercises.
        # See docs/decisions/005 for the full writeup. Do not add a 'death'
        # milestone assertion without re-reading that decision first.

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print(f"PASS: {len(records)} milestone records, types={sorted(set(types_seen))}")
    sys.exit(0)


if __name__ == "__main__":
    main()
