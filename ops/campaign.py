#!/usr/bin/env python3
"""Phase 1 campaign driver (PLAN.md §9 Phase 1 exit criterion: the
>=500-game campaign). Parallel harness over ops/runner.py's run_game() --
mirrors ops/throughput-probe.py's ProcessPoolExecutor pattern, but drives
the real state machine (write-ahead manifest, turn-budget/hang/wall-cap
classification into one of the ten §6 terminal statuses) instead of a bare
/usr/bin/time wrapper, and writes each run into its own directory under
data/runs/ for ops/collector.py to reconcile afterward.

Seed streams (§2 step 2: character RNG is "a dedicated ... seed ...
separate from the game seed"): char_seed and game_seed are two disjoint
integer ranges (default bases 0 and 500000) advanced by the same run index,
never mixed -- combos.py never reads game_seed and crawl's -seed never
touches char_seed, so keeping the ranges visibly non-overlapping is a
belt-and-suspenders readability choice, not a correctness requirement.

Resumable by construction: run_id is deterministic in (--run-prefix,
--index-start + i), so re-invoking with the same arguments after an
interruption skips every run_id that already has a result.json (no
wasted replay) and safely retries any that only got as far as manifest.json
(interrupted mid-run) by moving the stale directory aside first --
crawl resumes into an existing save under the same -dir/-name instead of
starting fresh, which would silently violate §6's "one game = one process
invocation, no resume into metrics", so a half-finished workdir is never
reused in place.

Library use: `run_campaign(n_games, ...) -> summary dict`.
CLI use: `campaign.py --n-games N [--workers N] [--turn-budget N]
[--wall-cap-secs N] [--hang-secs N] [--run-prefix STR] [--index-start N]
[--runs-dir DIR] [--out PATH]`.
"""
import argparse
import importlib.util
import json
import pathlib
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))

_spec = importlib.util.spec_from_file_location("runner", str(ROOT / "ops/runner.py"))
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

DEFAULT_RUNS_DIR = ROOT / "data/runs"
DEFAULT_CHAR_SEED_BASE = 0
DEFAULT_GAME_SEED_BASE = 500_000


def _ensure_fresh_workdir(workdir):
    """A workdir with a manifest.json but no result.json is a run that was
    interrupted mid-flight (killed process, machine restart) -- retrying in
    place would have crawl resume the existing save under the same
    -dir/-name instead of starting a fresh game (§6: no resume into
    metrics). Move it aside (never delete) so a retry always starts clean."""
    if not workdir.exists():
        return
    stale = workdir.with_name(workdir.name + f".stale-{int(time.time() * 1000)}")
    workdir.rename(stale)
    print(f"  [{workdir.name}] interrupted run found, moved aside to {stale.name}")


def _run_one(run_id, char_seed, game_seed, workdir, turn_budget, wall_cap_secs, hang_secs,
             bugfix_lua_errors=True, bugfix_indefinite_transform=True):
    manifest, digest = runner.combos.load_manifest()
    row = runner.rc_gen.build_manifest_row(run_id, char_seed, game_seed, manifest, digest)
    return runner.run_game(row, workdir, turn_budget=turn_budget,
                            wall_cap_secs=wall_cap_secs, hang_secs=hang_secs,
                            bugfix_lua_errors=bugfix_lua_errors,
                            bugfix_indefinite_transform=bugfix_indefinite_transform)


def run_campaign(n_games, *, workers=8, turn_budget=0,
                  wall_cap_secs=runner.DEFAULT_WALL_CAP_SECS,
                  hang_secs=runner.DEFAULT_HANG_SECS,
                  run_prefix="campaign", index_start=0,
                  char_seed_base=DEFAULT_CHAR_SEED_BASE,
                  game_seed_base=DEFAULT_GAME_SEED_BASE,
                  runs_dir=DEFAULT_RUNS_DIR,
                  bugfix_lua_errors=True, bugfix_indefinite_transform=True, char_seeds=None):
    """char_seeds, if given, overrides the default contiguous
    char_seed_base+i / game_seed_base+i allocation with an explicit list of
    char_seed ints (game_seed = game_seed_base + char_seed for each) --
    ops/experiment.py's seed-split selection produces exactly this shape,
    for a §8 experiment that needs a specific (possibly non-contiguous)
    subset of seeds rather than "the next n_games in order". n_games/
    index_start are ignored when char_seeds is given; run_id is keyed by
    char_seed directly so re-invoking with the same list is still
    resumable via the same result.json-exists skip below."""
    if not runner.CRAWL_BIN.exists():
        raise SystemExit(f"campaign.py: {runner.CRAWL_BIN} not found; build it first")

    runs_dir = pathlib.Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)

    if char_seeds is not None:
        id_seed_pairs = [(f"{run_prefix}-{cs:07d}", cs) for cs in char_seeds]
    else:
        id_seed_pairs = [(f"{run_prefix}-{i:06d}", char_seed_base + i)
                          for i in range(index_start, index_start + n_games)]

    jobs = []
    n_skipped = 0
    for run_id, char_seed in id_seed_pairs:
        workdir = runs_dir / run_id
        if (workdir / "result.json").exists():
            n_skipped += 1
            continue
        if workdir.exists():
            _ensure_fresh_workdir(workdir)
        game_seed = game_seed_base + char_seed
        jobs.append((run_id, char_seed, game_seed, workdir))

    range_desc = (f"{len(char_seeds)} explicit char_seeds" if char_seeds is not None
                  else f"index {index_start}..{index_start + n_games - 1}")
    print(f"campaign.py: {len(jobs)} run(s) to launch, {n_skipped} already complete "
          f"(prefix={run_prefix!r}, {range_desc}), "
          f"workers={workers}, turn_budget={turn_budget}, wall_cap_secs={wall_cap_secs}, "
          f"bugfix_lua_errors={bugfix_lua_errors}, "
          f"bugfix_indefinite_transform={bugfix_indefinite_transform}")

    results = []
    start = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(_run_one, run_id, char_seed, game_seed, workdir,
                      turn_budget, wall_cap_secs, hang_secs, bugfix_lua_errors,
                      bugfix_indefinite_transform): run_id
            for run_id, char_seed, game_seed, workdir in jobs
        }
        for fut in as_completed(futs):
            run_id = futs[fut]
            try:
                r = fut.result()
            except Exception as e:
                r = {"run_id": run_id, "status": "harness_failure", "detail": f"worker exception: {e}"}
            results.append(r)
            elapsed = time.time() - start
            print(f"  [{len(results)}/{len(jobs)}] {run_id} status={r.get('status')} "
                  f"wall={r.get('wall_secs')}s (campaign elapsed {elapsed:.0f}s)")

    status_counts = {}
    for r in results:
        status_counts[r.get("status", "unknown")] = status_counts.get(r.get("status", "unknown"), 0) + 1

    return {
        "n_requested": len(char_seeds) if char_seeds is not None else n_games,
        "n_launched": len(jobs),
        "n_skipped_already_complete": n_skipped,
        "workers": workers,
        "turn_budget": turn_budget,
        "wall_cap_secs": wall_cap_secs,
        "hang_secs": hang_secs,
        "bugfix_lua_errors": bugfix_lua_errors,
        "bugfix_indefinite_transform": bugfix_indefinite_transform,
        "run_prefix": run_prefix,
        "index_range": None if char_seeds is not None else [index_start, index_start + n_games - 1],
        "wall_secs_total": time.time() - start,
        "status_counts": status_counts,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-games", type=int,
                     help="required unless --seeds-file is given")
    ap.add_argument("--seeds-file",
                     help="JSON file: a list of explicit char_seed ints, overriding the "
                          "default contiguous char-seed-base/n-games/index-start allocation "
                          "(see ops/experiment.py's seed splits)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--turn-budget", type=int, default=0)
    ap.add_argument("--wall-cap-secs", type=int, default=runner.DEFAULT_WALL_CAP_SECS)
    ap.add_argument("--hang-secs", type=int, default=runner.DEFAULT_HANG_SECS)
    ap.add_argument("--run-prefix", default="campaign")
    ap.add_argument("--index-start", type=int, default=0)
    ap.add_argument("--char-seed-base", type=int, default=DEFAULT_CHAR_SEED_BASE)
    ap.add_argument("--game-seed-base", type=int, default=DEFAULT_GAME_SEED_BASE)
    ap.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    ap.add_argument("--out", help="write the run summary JSON here")
    ap.add_argument("--disable-bugfix-lua-errors", action="store_true",
                     help="reproduce the original qw crashes (docs/decisions/011); "
                          "for the Phase 2 A/B experiment's control arm")
    ap.add_argument("--disable-bugfix-indefinite-transform", action="store_true",
                     help="reproduce the original qw indefinite-transform rest stall "
                          "(docs/decisions/012); for the Phase 2 A/B experiment's control arm")
    args = ap.parse_args()

    char_seeds = None
    if args.seeds_file:
        char_seeds = json.loads(pathlib.Path(args.seeds_file).read_text())
    elif args.n_games is None:
        ap.error("--n-games is required unless --seeds-file is given")

    summary = run_campaign(
        args.n_games, workers=args.workers, turn_budget=args.turn_budget,
        wall_cap_secs=args.wall_cap_secs, hang_secs=args.hang_secs,
        run_prefix=args.run_prefix, index_start=args.index_start,
        char_seed_base=args.char_seed_base, game_seed_base=args.game_seed_base,
        runs_dir=args.runs_dir, bugfix_lua_errors=not args.disable_bugfix_lua_errors,
        bugfix_indefinite_transform=not args.disable_bugfix_indefinite_transform,
        char_seeds=char_seeds,
    )
    text = json.dumps(summary, indent=2, default=str)
    print(text)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
