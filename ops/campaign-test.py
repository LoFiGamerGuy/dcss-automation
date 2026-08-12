#!/usr/bin/env python3
"""Phase 1 exit-criterion test for ops/campaign.py: the parallel-isolation
check ("N workers, zero cross-contamination") plus a resumability check
("interrupted campaign re-invoked with the same args replays nothing that
already completed").

Runs a small real batch (real pinned binary, real concurrent workers) with
a short --turn-budget so it finishes in seconds, then asserts, per run:
  1. manifest.json/result.json run_id matches its own directory name;
  2. the sampled character recorded in manifest.json is exactly what
     combos.sample_character(char_seed) recomputes standalone -- if a
     concurrent worker had clobbered another run's manifest this would
     diverge;
  3. char_seed/game_seed are unique across the whole batch (no collisions
     from the driver's own seed-stream arithmetic);
  4. no file anywhere under this run's directory tree mentions a *different*
     run's run_id -- the concrete signature of true cross-contamination
     (one worker's save/rc data leaking into another's directory).
Then re-invokes run_campaign() with identical arguments and asserts nothing
new is launched (n_launched == 0, n_skipped == every run from the first pass).

Usage: campaign-test.py
Exit 0 and prints "PASS" on success; exit 1 with the failure(s) on failure.
"""
import importlib.util
import json
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
import combos  # noqa: E402

_spec = importlib.util.spec_from_file_location("campaign", str(ROOT / "ops/campaign.py"))
campaign = importlib.util.module_from_spec(_spec)
# ProcessPoolExecutor pickles submitted functions by (module name, qualname)
# and resolves that via sys.modules in both the submitting and the worker
# process -- module_from_spec() alone does not register the module there
# (unlike a normal `import`), so without this, pickling campaign._run_one
# fails immediately (every task comes back a harness_failure with no wall
# time at all, not a real game failure -- caught while first running this
# test).
sys.modules["campaign"] = campaign
_spec.loader.exec_module(campaign)

N_GAMES = 12
WORKERS = 6
TURN_BUDGET = 25
RUN_PREFIX = "isotest"


def main():
    if not campaign.runner.CRAWL_BIN.exists():
        print(f"campaign-test.py: {campaign.runner.CRAWL_BIN} not found; build it first",
              file=sys.stderr)
        sys.exit(1)

    failures = []
    tmp = tempfile.mkdtemp(prefix="dcss-campaign-test-")
    runs_dir = pathlib.Path(tmp)
    # Deliberately drive the campaign through a *relative* runs_dir: an
    # absolute mkdtemp path masked the 2026-08-12 pilot-contamination bug
    # (relative -rc/-dir/-morgue resolved against crawl's cwd => rc never
    # found => every game hung at the welcome screen). rc-gen now resolves
    # workdir to absolute; this keeps the relative-caller path exercised.
    runs_dir_arg = pathlib.Path(os.path.relpath(runs_dir, os.getcwd()))
    try:
        summary1 = campaign.run_campaign(
            N_GAMES, workers=WORKERS, turn_budget=TURN_BUDGET,
            run_prefix=RUN_PREFIX, runs_dir=runs_dir_arg,
        )
        if summary1["n_launched"] != N_GAMES:
            failures.append(f"first pass launched {summary1['n_launched']}, expected {N_GAMES}")

        run_dirs = sorted(runs_dir.glob(f"{RUN_PREFIX}-*"))
        if len(run_dirs) != N_GAMES:
            failures.append(f"expected {N_GAMES} run directories, found {len(run_dirs)}")

        manifest, digest = combos.load_manifest()
        seen_char_seeds, seen_game_seeds = set(), set()
        run_ids = [d.name for d in run_dirs]

        for workdir in run_dirs:
            run_id = workdir.name
            mrow = json.loads((workdir / "manifest.json").read_text())
            rrow = json.loads((workdir / "result.json").read_text())

            if mrow.get("run_id") != run_id:
                failures.append(f"{run_id}: manifest.json run_id={mrow.get('run_id')!r} "
                                 f"!= directory name")
            if rrow.get("run_id") != run_id:
                failures.append(f"{run_id}: result.json run_id={rrow.get('run_id')!r} "
                                 f"!= directory name")

            char_seed = mrow.get("char_seed")
            game_seed = mrow.get("game_seed")
            if char_seed in seen_char_seeds:
                failures.append(f"{run_id}: char_seed {char_seed} reused by another run in the batch")
            seen_char_seeds.add(char_seed)
            if game_seed in seen_game_seeds:
                failures.append(f"{run_id}: game_seed {game_seed} reused by another run in the batch")
            seen_game_seeds.add(game_seed)

            expected_char = combos.sample_character(manifest, digest, char_seed)
            if mrow.get("character") != expected_char:
                failures.append(
                    f"{run_id}: manifest character {mrow.get('character')} != recomputed "
                    f"{expected_char} for char_seed={char_seed} -- possible cross-write")

            other_run_ids = [r for r in run_ids if r != run_id]
            for f in workdir.rglob("*"):
                if not f.is_file():
                    continue
                try:
                    text = f.read_text(errors="ignore")
                except Exception:
                    continue
                for other in other_run_ids:
                    if other in text:
                        failures.append(f"{run_id}: file {f.relative_to(workdir)} mentions "
                                         f"another run's id {other!r} -- cross-contamination")

        summary2 = campaign.run_campaign(
            N_GAMES, workers=WORKERS, turn_budget=TURN_BUDGET,
            run_prefix=RUN_PREFIX, runs_dir=runs_dir,
        )
        if summary2["n_launched"] != 0:
            failures.append(f"resume pass launched {summary2['n_launched']} runs that should "
                             f"already have been complete")
        if summary2["n_skipped_already_complete"] != N_GAMES:
            failures.append(f"resume pass skipped {summary2['n_skipped_already_complete']}, "
                             f"expected {N_GAMES}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print(f"PASS: {N_GAMES} concurrent runs ({WORKERS} workers) all self-consistent, "
          f"zero cross-contamination, resume pass replayed nothing")
    sys.exit(0)


if __name__ == "__main__":
    main()
