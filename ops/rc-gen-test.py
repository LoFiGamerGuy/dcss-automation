#!/usr/bin/env python3
"""Integration smoke test for ops/rc-gen.py: for a handful of char_seeds
(chosen to cover both a plain combo and a weapon-choice combo — see the
CASES table), build a run via rc-gen.py, materialize it, and confirm the
pinned crawl binary actually accepts the generated rc and reaches its
"Welcome," banner. This is deliberately not a full canary (no play budget) —
it only proves the sampler -> rc-gen -> crawl handoff works, since a broken
rc (bad combo syntax, bad weapon name, missing include) fails before that
banner ever appears.

Usage: rc-gen-test.py
Exit 0 and prints "PASS" on success; exit 1 with the failure(s) on failure.

Note: the 20s "Welcome," timeout ops/run-canary.py and ops/telemetry-test.py
use was measured with no other crawl processes competing for CPU/disk; under
a concurrent 8-worker throughput campaign, even 40s produced one empirical
flake (confirmed harmless by hand: the run had actually reached "Welcome,"
and full chargen in a manual re-run under the same load, just slower than
the timeout) — this test uses 60s for headroom.
"""
import pathlib
import sys
import tempfile

import pexpect

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
import combos  # noqa: E402
import importlib.util

spec = importlib.util.spec_from_file_location("rc_gen", str(ROOT / "ops/rc-gen.py"))
rc_gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc_gen)

CRAWL_BIN = ROOT / "vendor/crawl/crawl-ref/source/crawl"
QW_DIR = ROOT / "vendor/qw"

# char_seeds hand-picked (by sampling combos.py offline) to cover one combo
# with no weapon choice and one with a weapon choice, so both rc_combo shapes
# ("SpJo" and "SpJo.weapon name") get exercised end to end.
CASES = [0, 1, 2, 3, 4]


def check_one(char_seed, manifest, digest):
    row = rc_gen.build_manifest_row(f"rcgentest{char_seed}", char_seed, 7000 + char_seed,
                                     manifest, digest)
    with tempfile.TemporaryDirectory(prefix="dcss-rcgentest-") as tmp:
        workdir = pathlib.Path(tmp)
        layout = rc_gen.write_run_dir(row, workdir)
        cmd = [str(CRAWL_BIN), "-rcdir", str(QW_DIR)] + layout["clo_args"]
        child = pexpect.spawn(" ".join(cmd), timeout=60, dimensions=(50, 130), cwd=str(workdir))
        try:
            child.expect(r"Welcome,", timeout=60)
            ok = True
            detail = f"combo={row['character']['rc_combo']!r} reached Welcome banner"
        except pexpect.TIMEOUT:
            ok = False
            detail = (f"combo={row['character']['rc_combo']!r} never reached Welcome "
                       f"banner; output tail={child.before[-500:]!r}")
        except pexpect.EOF:
            ok = False
            detail = (f"combo={row['character']['rc_combo']!r} process exited before "
                       f"Welcome banner; output tail={child.before[-500:]!r}")
        finally:
            try:
                if child.isalive():
                    child.terminate(force=True)
                    child.wait()
            except Exception:
                pass
        return ok, detail


def main():
    if not CRAWL_BIN.exists():
        print(f"rc-gen-test.py: {CRAWL_BIN} not found; build it first", file=sys.stderr)
        sys.exit(1)

    manifest, digest = combos.load_manifest()
    failures = []
    weapon_combo_seen = False
    plain_combo_seen = False

    for char_seed in CASES:
        ok, detail = check_one(char_seed, manifest, digest)
        print(("ok  " if ok else "FAIL") + f" char_seed={char_seed}: {detail[:200]}")
        if not ok:
            failures.append(detail)
        character = combos.sample_character(manifest, digest, char_seed)
        if character["weapon"] is not None:
            weapon_combo_seen = True
        else:
            plain_combo_seen = True

    if not weapon_combo_seen:
        failures.append(f"CASES={CASES} never sampled a weapon-choice combo — "
                         f"extend CASES so the '.weapon' rc syntax is exercised")
    if not plain_combo_seen:
        failures.append(f"CASES={CASES} never sampled a no-weapon-choice combo — "
                         f"extend CASES so the plain-combo rc syntax is exercised")

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print(f"PASS: {len(CASES)} sampled runs all reached crawl's Welcome banner "
          f"(weapon combo and plain combo both covered)")
    sys.exit(0)


if __name__ == "__main__":
    main()
