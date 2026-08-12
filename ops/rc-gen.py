#!/usr/bin/env python3
"""Per-run rc generation (PLAN.md §5's adapter.py, the launch-artifact slice
of it): combines the §2 sampler (ops/combos.py) with
ops/campaign.rc.tmpl to produce everything one campaign run needs to launch
— the resolved character, the write-ahead manifest row §6 requires before
launch, and the rc/save/morgue directory layout.

This is *not* the runner state machine (§6: terminal-status classification,
hang detection, accounting reconciliation) — that still needs to be built.
It's the independently testable piece of it: "given these seeds, what rc do
we hand crawl, and does crawl accept it."

Library use: `build_manifest_row(...)`, `write_run_dir(...)`.
CLI use: `rc-gen.py --run-id ID --char-seed N --game-seed N [--workdir DIR]`
prints the manifest row as JSON; with --workdir, also materializes run.rc
plus empty saves/morgue dirs there and includes the crawl CLO args to launch
it (rcdir/binary path are the caller's concern, same split as
ops/run-canary.py and ops/throughput-probe.py use today).
"""
import argparse
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
import combos  # noqa: E402

RC_TMPL_PATH = ROOT / "ops/campaign.rc.tmpl"


def build_manifest_row(run_id, char_seed, game_seed, manifest=None, digest=None):
    """The write-ahead manifest row §6 requires committed before launch: run
    ID, character, seeds, all version/config hashes."""
    if manifest is None:
        manifest, digest = combos.load_manifest()
    character = combos.sample_character(manifest, digest, char_seed)
    rc_tmpl_text = RC_TMPL_PATH.read_text()
    return {
        "run_id": run_id,
        "char_seed": char_seed,
        "game_seed": game_seed,
        "character": character,
        "crawl_commit": manifest["crawl_commit"],
        "rc_tmpl_sha256": hashlib.sha256(rc_tmpl_text.encode()).hexdigest(),
    }


def write_run_dir(row, workdir, turn_budget=0, bugfix_lua_errors=True,
                   bugfix_indefinite_transform=True):
    """Materialize the rc file + save/morgue dirs a launch needs. Returns the
    crawl CLO args a caller appends to its binary/-rcdir invocation.
    turn_budget=0 disables the harness turn-budget quit (see
    campaign.rc.tmpl) — the default, so existing callers that don't pass it
    (rc-gen-test.py) keep testing the sampler->rc->crawl handoff only.

    bugfix_lua_errors (default True) controls docs/decisions/011's
    QW_BUGFIX_LUA_ERRORS rc flag — the Phase 2 A/B toggle for the two qw
    upstream Lua-crash fixes. False reproduces the original crashes, for an
    experiment's control arm.

    bugfix_indefinite_transform (default True) controls docs/decisions/012's
    QW_BUGFIX_INDEFINITE_TRANSFORM rc flag — the Phase 2 A/B toggle for the
    plans-rest.lua indefinite-talisman-transform stall fix (every
    Shapeshifter game stuck resting forever in beast-form). False
    reproduces the original stall, for an experiment's control arm.

    workdir is resolved to an absolute path because the returned clo_args
    are stringified into crawl's command line while runner.monitor_game
    spawns crawl with cwd=workdir: a relative workdir made crawl resolve
    -rc/-dir/-morgue against *its own* cwd, so the rc was never found, qw
    never loaded, and every game hung silently at the welcome screen (the
    2026-08-12 pilot contamination — both batches, wrongly blamed on host
    contention the first time)."""
    workdir = pathlib.Path(workdir).resolve()
    rc_text = (RC_TMPL_PATH.read_text()
               .replace("__COMBO__", row["character"]["rc_combo"])
               .replace("__TURN_BUDGET__", str(turn_budget))
               .replace("__BUGFIX_LUA_ERRORS__", "true" if bugfix_lua_errors else "false")
               .replace("__BUGFIX_INDEFINITE_TRANSFORM__",
                        "true" if bugfix_indefinite_transform else "false"))
    rc_path = workdir / "run.rc"
    rc_path.write_text(rc_text)
    save_dir = workdir / "saves"
    morgue_dir = workdir / "morgue"
    save_dir.mkdir(parents=True, exist_ok=True)
    morgue_dir.mkdir(parents=True, exist_ok=True)
    return {
        "rc_path": rc_path,
        "save_dir": save_dir,
        "morgue_dir": morgue_dir,
        "clo_args": [
            "-lua-max-memory", "128",
            "-rc", str(rc_path),
            "-name", row["run_id"],
            "-seed", str(row["game_seed"]),
            "-dir", str(save_dir),
            "-morgue", str(morgue_dir),
            "-no-player-bones",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--char-seed", type=int, required=True)
    ap.add_argument("--game-seed", type=int, required=True)
    ap.add_argument("--workdir", help="if given, materialize run.rc/saves/morgue here")
    ap.add_argument("--turn-budget", type=int, default=0,
                     help="harness turn-budget quit (0 disables); see campaign.rc.tmpl")
    ap.add_argument("--disable-bugfix-lua-errors", action="store_true",
                     help="reproduce the original qw crashes (docs/decisions/011); "
                          "for the Phase 2 A/B experiment's control arm")
    ap.add_argument("--disable-bugfix-indefinite-transform", action="store_true",
                     help="reproduce the original qw indefinite-transform rest stall "
                          "(docs/decisions/012); for the Phase 2 A/B experiment's control arm")
    args = ap.parse_args()

    row = build_manifest_row(args.run_id, args.char_seed, args.game_seed)
    if args.workdir:
        layout = write_run_dir(row, args.workdir, turn_budget=args.turn_budget,
                                bugfix_lua_errors=not args.disable_bugfix_lua_errors,
                                bugfix_indefinite_transform=
                                not args.disable_bugfix_indefinite_transform)
        row["clo_args"] = layout["clo_args"]
    print(json.dumps(row, default=str))


if __name__ == "__main__":
    main()
