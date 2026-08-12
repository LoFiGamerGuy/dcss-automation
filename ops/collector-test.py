#!/usr/bin/env python3
"""Phase 1 exit-criterion test for ops/collector.py + ops/report.py: the
reconciliation invariant ("every scheduled run appears exactly once with a
terminal status", a manifest with no result never silently dropped) and
report byte-identical reproducibility from the DB. Uses hand-built synthetic
manifest.json/result.json fixtures rather than a real campaign -- this tests
the collector/report logic itself, not crawl; ops/runner-drills-test.py and
the spot-check in docs/JOURNAL.md already prove runner.py produces exactly
this manifest/result shape against the real binary.

Fixtures (4 runs):
  - won1:    HuFi (Human/Fighter/melee), status=won, 3 runes, enters+ends Lair
  - died1:   MuHu (Mummy/Hunter/utility), status=died
  - pending1: DEHW (Deep Elf/Hedge Wizard/caster), manifest only, started_at
    = now (still within its own wall_cap_secs+hang_secs budget)
  - orphan1: HuFi again, manifest only, started_at = long ago (past its
    budget + grace buffer) -- the "runner process was killed externally"
    case, not "still running"

Usage: collector-test.py
Exit 0 and prints "PASS" on success; exit 1 with the failure(s) on failure.
"""
import importlib.util
import json
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


collector = _load("collector", "ops/collector.py")
report = _load("report", "ops/report.py")

CRAWL_COMMIT = json.loads((ROOT / "data/manifests/legal-characters.json").read_text())["crawl_commit"]


def _manifest_row(run_id, char_seed, combo, weapon=None, started_at=None,
                   wall_cap_secs=1800, hang_secs=120):
    return {
        "run_id": run_id, "char_seed": char_seed, "game_seed": char_seed,
        "character": {
            "manifest_sha256": "deadbeef", "char_seed": char_seed, "pair_index": 0,
            "combo": combo, "weapon_index": None, "weapon": weapon,
            "rc_combo": f"{combo}.{weapon}" if weapon else combo,
        },
        "crawl_commit": CRAWL_COMMIT, "rc_tmpl_sha256": "cafef00d",
        "turn_budget": 0, "wall_cap_secs": wall_cap_secs, "hang_secs": hang_secs,
        "started_at": started_at if started_at is not None else time.time(),
    }


def _result_row(run_id, status, logfile_row=None, wall_secs=10.0, output_bytes=1000):
    return {"run_id": run_id, "status": status, "detail": f"test fixture: {status}",
            "logfile_row": logfile_row, "wall_secs": wall_secs, "output_bytes": output_bytes}


def _write_run(runs_dir, run_id, manifest_row, result_row=None, milestones=None):
    workdir = runs_dir / run_id
    workdir.mkdir(parents=True)
    (workdir / "manifest.json").write_text(json.dumps(manifest_row))
    if result_row is not None:
        (workdir / "result.json").write_text(json.dumps(result_row))
    if milestones:
        mdir = workdir / "saves" / "saves"
        mdir.mkdir(parents=True)
        lines = []
        for m in milestones:
            lines.append(":".join(f"{k}={v}" for k, v in m.items()))
        (mdir / "milestones-seeded").write_text("\n".join(lines) + "\n")


def main():
    failures = []
    now = time.time()

    with tempfile.TemporaryDirectory(prefix="dcss-collector-test-") as tmp:
        tmp = pathlib.Path(tmp)
        runs_dir = tmp / "runs"
        runs_dir.mkdir()

        _write_run(
            runs_dir, "won1", _manifest_row("won1", 1, "HuFi"),
            _result_row("won1", "won", {
                "place": "Zot:5", "br": "Zot", "lvl": "5", "absdepth": "26",
                "xl": "27", "turn": "80000", "aut": "300000", "sc": "5000000",
                "urune": "3", "ktyp": "winning",
            }),
            milestones=[
                {"type": "begin", "milestone": "began the quest for the Orb."},
                {"type": "br.enter", "place": "Lair:1", "br": "Lair", "oplace": "D:9"},
                {"type": "br.end", "place": "Lair:8", "br": "Lair"},
            ],
        )
        _write_run(
            runs_dir, "died1", _manifest_row("died1", 2, "MuHu"),
            _result_row("died1", "died", {
                "place": "D:7", "br": "D", "lvl": "7", "absdepth": "7",
                "xl": "5", "turn": "500", "aut": "5000", "sc": "200",
                "ktyp": "mon", "killer": "a kobold",
            }),
        )
        _write_run(
            runs_dir, "pending1",
            _manifest_row("pending1", 3, "DEHW", started_at=now - 5),
        )
        _write_run(
            runs_dir, "orphan1",
            _manifest_row("orphan1", 4, "HuFi", started_at=now - 100000),
        )

        # --- non-strict build: pending1 stays pending, orphan1 (past its
        # own budget + grace) is attributed as harness_failure. ---
        db_path = tmp / "campaign.db"
        summary = collector.build_db(runs_dir, db_path, strict=False, now=now)

        if summary["n_manifests"] != 4:
            failures.append(f"expected 4 manifests, got {summary['n_manifests']}")
        if summary["n_reconciled"] != 2:
            failures.append(f"expected 2 reconciled, got {summary['n_reconciled']}")
        if summary["n_pending"] != 1:
            failures.append(f"expected 1 pending, got {summary['n_pending']}")
        if summary["n_harness_failure_missing_result"] != 1:
            failures.append("expected 1 harness_failure-from-missing-result, got "
                             f"{summary['n_harness_failure_missing_result']}")
        if not summary["invariant_holds"]:
            failures.append(f"reconciliation invariant should hold (non-strict): {summary}")

        # --- strict build: both unreconciled runs collapse to harness_failure. ---
        db_path_strict = tmp / "campaign-strict.db"
        summary_strict = collector.build_db(runs_dir, db_path_strict, strict=True, now=now)
        if summary_strict["n_pending"] != 0:
            failures.append(f"strict build should have 0 pending, got {summary_strict['n_pending']}")
        if summary_strict["n_harness_failure_missing_result"] != 2:
            failures.append("strict build should attribute both unreconciled runs as "
                             f"harness_failure, got {summary_strict['n_harness_failure_missing_result']}")
        if not summary_strict["invariant_holds"]:
            failures.append(f"reconciliation invariant should hold (strict): {summary_strict}")

        # --- report: stratification correctness (against the non-strict DB) ---
        rpt = report.generate(db_path)

        overall = rpt["overall"]
        if overall["n"] != 4:
            failures.append(f"report overall n should be 4, got {overall['n']}")
        if overall["status_counts"].get("won") != 1 or overall["status_counts"].get("died") != 1:
            failures.append(f"unexpected overall status_counts: {overall['status_counts']}")
        if overall["status_counts"].get("pending") != 1:
            failures.append(f"expected 1 pending in overall status_counts: {overall['status_counts']}")
        if overall["status_counts"].get("harness_failure") != 1:
            failures.append(f"expected 1 harness_failure in overall status_counts: {overall['status_counts']}")
        if abs((overall["rune_rate"] or 0) - 0.25) > 1e-9:
            failures.append(f"expected overall rune_rate 0.25 (1/4 runs with urune>0), got {overall['rune_rate']}")

        lair = overall["branches"].get("Lair")
        if not lair or lair["entered_n"] != 1 or lair["end_reached_n"] != 1:
            failures.append(f"expected Lair entered_n=1/end_reached_n=1 in overall branches, got {lair}")

        by_species = rpt["by_species"]
        if by_species.get("Human", {}).get("n") != 2:
            failures.append(f"expected 2 Human runs (won1+orphan1), got {by_species.get('Human')}")
        if by_species.get("Mummy", {}).get("n") != 1:
            failures.append(f"expected 1 Mummy run, got {by_species.get('Mummy')}")
        if by_species.get("Deep Elf", {}).get("n") != 1:
            failures.append(f"expected 1 Deep Elf run, got {by_species.get('Deep Elf')}")

        by_background = rpt["by_background"]
        if by_background.get("Fighter", {}).get("n") != 2:
            failures.append(f"expected 2 Fighter runs, got {by_background.get('Fighter')}")

        by_archetype = rpt["by_archetype"]
        if by_archetype.get("melee", {}).get("n") != 2:
            failures.append(f"expected 2 melee runs (Fighter x2), got {by_archetype.get('melee')}")
        if by_archetype.get("utility", {}).get("n") != 1:
            failures.append(f"expected 1 utility run (Hunter), got {by_archetype.get('utility')}")
        if by_archetype.get("caster", {}).get("n") != 1:
            failures.append(f"expected 1 caster run (Hedge Wizard), got {by_archetype.get('caster')}")

        # --- report byte-identical reproducibility from the DB ---
        text1 = json.dumps(report.generate(db_path), indent=2, sort_keys=True)
        text2 = json.dumps(report.generate(db_path), indent=2, sort_keys=True)
        if text1 != text2:
            failures.append("report.generate() is not byte-identical across repeated calls "
                             "against the same unchanged DB")

    if failures:
        print("FAIL:")
        for f in failures:
            print(f" - {f}")
        sys.exit(1)

    print("PASS: reconciliation invariant (strict + non-strict), stratification "
          "correctness, and report byte-identical reproducibility all verified")
    sys.exit(0)


if __name__ == "__main__":
    main()
