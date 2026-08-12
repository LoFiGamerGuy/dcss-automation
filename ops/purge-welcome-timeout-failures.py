#!/usr/bin/env python3
"""Delete run directories whose result.json is the specific intermittent
"no 'Welcome,' banner within Ns (chargen stuck or crashed)" harness_failure
(docs/decisions/013 -- root cause not pinned down, but confirmed real and
confirmed NOT tied to any run's own character/seed: it's a startup-time
race, not a reproducible-per-character bug) so a subsequent campaign.py
invocation with the same --run-prefix/--seeds-file naturally retries
exactly those runs via its existing resume-by-run_id logic, and nothing
else.

Deliberately narrow: only purges this one specific detail string, not
every harness_failure (a real crash-with-no-logfile-row harness_failure
should NOT be silently retried into oblivion -- only the specific
known-intermittent chargen-freeze one).

CLI use: `purge-welcome-timeout-failures.py --runs-dir DIR --run-prefix STR`
prints the count purged; a caller loops this + a campaign.py re-invocation
until the count is zero or a retry budget is exhausted.
"""
import argparse
import json
import pathlib
import shutil


def purge(runs_dir, run_prefix):
    runs_dir = pathlib.Path(runs_dir)
    purged = []
    for workdir in sorted(runs_dir.glob(f"{run_prefix}-*")):
        result_path = workdir / "result.json"
        if not result_path.exists():
            continue
        try:
            result = json.loads(result_path.read_text())
        except Exception:
            continue
        if (result.get("status") == "harness_failure"
                and "no 'Welcome,' banner within" in (result.get("detail") or "")):
            shutil.rmtree(workdir)
            purged.append(workdir.name)
    return purged


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs-dir", required=True)
    ap.add_argument("--run-prefix", required=True)
    args = ap.parse_args()
    purged = purge(args.runs_dir, args.run_prefix)
    print(f"purged {len(purged)} welcome-timeout harness_failure run(s)")
    for name in purged:
        print(f"  {name}")


if __name__ == "__main__":
    main()
