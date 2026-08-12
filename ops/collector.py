#!/usr/bin/env python3
"""Phase 1 collector (PLAN.md §6 run accounting): reconciles per-run
`manifest.json`/`result.json` pairs under a runs directory (default
`data/runs/`, one subdirectory per `ops/runner.py` invocation) into a single
SQLite database.

Reconciliation invariant (§6): "every scheduled run appears exactly once
with a terminal status" — a manifest with no matching result.json is never
silently dropped. Two cases look the same from outside (no result.json yet)
but mean different things:
  - the run is still in flight (runner.py hasn't finished) -- reported as
    `status="pending"`, excluded from the invariant check;
  - the runner process was killed/crashed before it could write
    result.json (external kill, OOM, machine reboot -- run_game() itself
    always writes result.json even on its own internal failures, so a
    missing file means the *process*, not just the game, died) --
    reported as `status="harness_failure"`, counted in the invariant as
    correctly attributed, not dropped.
The distinction is a grace-period heuristic off the manifest's own
`started_at`/`wall_cap_secs`/`hang_secs` (no PID is recorded, so liveness
can't be checked directly): if less time than the run's own worst-case
budget plus a fixed buffer has elapsed, it's still plausibly running.
`--strict` (what a campaign driver should pass once it knows every worker
has exited) collapses this: anything still unreconciled is `harness_failure`
regardless of age.

Species/background/weapon are decoded from the sampled combo string against
the manifest referenced by the run's own `crawl_commit` pin
(`data/manifests/legal-characters.json` -- this repo only ever has one
pinned commit at a time, but the lookup is keyed and will loudly mismatch
rather than silently misdecode if that ever changes). Archetype is a fixed
lookup table -- see docs/decisions/007-archetype-classification.md for how
it was derived and why it's not in crawl's own data.

Per-run milestone events (DGL_MILESTONES file, `<workdir>/saves/saves/
milestones-seeded`) are stored alongside the terminal-status row so the
outcome vector's per-branch entered/branch-end-reached indicators (PLAN §1)
can be derived at report time from `br.enter`/`br.end` records, not just the
single final logfile row (which only carries the *last* place, not the
history of branches visited).

Library use: `build_db(runs_dir, db_path, strict=False)`.
CLI use: `collector.py [--runs-dir DIR] [--db PATH] [--strict]`; prints a
one-line reconciliation summary and exits 1 if the invariant is violated
under --strict.
"""
import argparse
import json
import pathlib
import sqlite3
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
import xlog  # noqa: E402

DEFAULT_RUNS_DIR = ROOT / "data/runs"
DEFAULT_DB_PATH = ROOT / "data/campaign.db"
MANIFEST_DIR = ROOT / "data/manifests"

# See docs/decisions/007-archetype-classification.md for how this table was
# derived (crawl-ref/source/job-data.h: weapon_choice != none, spells > 0).
JOB_ARCHETYPE = {
    "AE": "caster", "Al": "caster", "Cj": "caster", "EE": "caster",
    "En": "caster", "FE": "caster", "HW": "caster", "Hs": "caster",
    "IE": "caster", "Ne": "caster", "Su": "caster",
    "CA": "hybrid", "Re": "hybrid", "Wr": "hybrid",
    "Fi": "melee", "Gl": "melee", "Be": "melee", "CK": "melee",
    "Mo": "melee", "De": "melee",
    "Ar": "utility", "Br": "utility", "Hu": "utility", "Sh": "utility",
    "Wn": "utility",
}

# Buffer added on top of a run's own wall_cap_secs+hang_secs before treating
# a missing result.json as a harness failure rather than "still running":
# covers the welcome-banner timeout, the graceful-save grace period, and
# process teardown/write overhead in monitor_game(), none of which are
# counted in wall_cap_secs/hang_secs themselves.
PENDING_GRACE_BUFFER_SECS = 180

SCHEMA = """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    char_seed INTEGER,
    game_seed INTEGER,
    combo TEXT,
    species TEXT,
    background TEXT,
    weapon TEXT,
    archetype TEXT,
    crawl_commit TEXT,
    rc_tmpl_sha256 TEXT,
    turn_budget INTEGER,
    wall_cap_secs INTEGER,
    hang_secs INTEGER,
    bugfix_lua_errors INTEGER,
    started_at REAL,
    reconciled INTEGER,
    status TEXT,
    detail TEXT,
    wall_secs REAL,
    output_bytes INTEGER,
    place TEXT,
    br TEXT,
    lvl INTEGER,
    absdepth INTEGER,
    xl INTEGER,
    turn INTEGER,
    aut INTEGER,
    sc INTEGER,
    urune INTEGER,
    ktyp TEXT,
    killer TEXT,
    kaux TEXT
);
CREATE TABLE milestones (
    run_id TEXT,
    seq INTEGER,
    type TEXT,
    place TEXT,
    br TEXT,
    oplace TEXT,
    turn INTEGER,
    milestone TEXT,
    raw_json TEXT
);
CREATE INDEX idx_milestones_run ON milestones(run_id);
CREATE INDEX idx_milestones_type ON milestones(type);
"""


def _species_job_lookup(crawl_commit):
    path = MANIFEST_DIR / "legal-characters.json"
    manifest = json.loads(path.read_text())
    if manifest["crawl_commit"] != crawl_commit:
        print(f"collector.py: WARNING run pinned to {crawl_commit} but "
              f"{path} is for {manifest['crawl_commit']} -- species/background "
              "names may be wrong", file=sys.stderr)
    species = {s["abbr"]: s["name"] for s in manifest["species"]}
    jobs = {j["abbr"]: j["name"] for j in manifest["jobs"]}
    return species, jobs


def _decode_combo(combo, species_lu, jobs_lu):
    sp_abbr, job_abbr = combo[:2], combo[2:4]
    return species_lu.get(sp_abbr, sp_abbr), jobs_lu.get(job_abbr, job_abbr), job_abbr


def _int_or_none(fields, key):
    v = fields.get(key)
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _load_milestones(workdir):
    mfile = workdir / "saves" / "saves" / "milestones-seeded"
    if not mfile.exists():
        return []
    records = []
    for line in mfile.read_text().splitlines():
        if not line.strip():
            continue
        try:
            records.append(xlog.parse_line(line))
        except Exception:
            continue
    return records


def _reconcile_status(manifest_row, has_result, result, run_age, strict):
    if has_result:
        return result["status"], result.get("detail", ""), 1
    if not strict and run_age < (
        manifest_row.get("wall_cap_secs", 1800)
        + manifest_row.get("hang_secs", 120)
        + PENDING_GRACE_BUFFER_SECS
    ):
        return "pending", f"no result.json yet, {run_age:.0f}s since start", 0
    return ("harness_failure",
            f"no result.json found ({run_age:.0f}s since start) -- "
            "runner process likely killed externally before finishing", 0)


def build_db(runs_dir, db_path, strict=False, now=None):
    """Rebuild the SQLite DB from scratch from every manifest.json under
    runs_dir. Idempotent and re-runnable: the JSON files, not the DB, are
    the source of truth, so there is no incremental-update state to get out
    of sync. Returns a summary dict."""
    runs_dir = pathlib.Path(runs_dir)
    db_path = pathlib.Path(db_path)
    if now is None:
        now = time.time()

    manifest_paths = sorted(runs_dir.glob("*/manifest.json"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)

    species_lu_cache = {}
    n_reconciled = n_pending = n_harness_failure_missing = 0

    for mpath in manifest_paths:
        workdir = mpath.parent
        run_id = workdir.name
        manifest_row = json.loads(mpath.read_text())
        rpath = workdir / "result.json"
        has_result = rpath.exists()
        result = json.loads(rpath.read_text()) if has_result else None

        run_age = now - manifest_row.get("started_at", now)
        status, detail, reconciled = _reconcile_status(
            manifest_row, has_result, result, run_age, strict)
        if status == "pending":
            n_pending += 1
        elif not reconciled:
            n_harness_failure_missing += 1
        else:
            n_reconciled += 1

        character = manifest_row.get("character", {})
        combo = character.get("combo", "")
        crawl_commit = manifest_row.get("crawl_commit", "")
        if crawl_commit not in species_lu_cache:
            species_lu_cache[crawl_commit] = _species_job_lookup(crawl_commit)
        species_lu, jobs_lu = species_lu_cache[crawl_commit]
        species, background, job_abbr = _decode_combo(combo, species_lu, jobs_lu)
        archetype = JOB_ARCHETYPE.get(job_abbr, "unknown")

        logfile_row = (result or {}).get("logfile_row") or {}

        bugfix_lua_errors = manifest_row.get("bugfix_lua_errors")
        conn.execute(
            "INSERT INTO runs VALUES (" + ",".join(["?"] * 32) + ")",
            (
                run_id,
                manifest_row.get("char_seed"),
                manifest_row.get("game_seed"),
                combo, species, background, character.get("weapon"), archetype,
                crawl_commit, manifest_row.get("rc_tmpl_sha256"),
                manifest_row.get("turn_budget"), manifest_row.get("wall_cap_secs"),
                manifest_row.get("hang_secs"),
                None if bugfix_lua_errors is None else int(bool(bugfix_lua_errors)),
                manifest_row.get("started_at"),
                reconciled, status, detail,
                (result or {}).get("wall_secs"), (result or {}).get("output_bytes"),
                logfile_row.get("place"), logfile_row.get("br"),
                _int_or_none(logfile_row, "lvl"), _int_or_none(logfile_row, "absdepth"),
                _int_or_none(logfile_row, "xl"), _int_or_none(logfile_row, "turn"),
                _int_or_none(logfile_row, "aut"), _int_or_none(logfile_row, "sc"),
                _int_or_none(logfile_row, "urune") or 0,
                logfile_row.get("ktyp"), logfile_row.get("killer"), logfile_row.get("kaux"),
            ),
        )

        for seq, rec in enumerate(_load_milestones(workdir)):
            conn.execute(
                "INSERT INTO milestones VALUES (?,?,?,?,?,?,?,?,?)",
                (run_id, seq, rec.get("type"), rec.get("place"), rec.get("br"),
                 rec.get("oplace"), _int_or_none(rec, "turn"), rec.get("milestone"),
                 json.dumps(rec, sort_keys=True)),
            )

    n_rows = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    conn.commit()
    conn.close()

    # Reconciliation invariant (§6): every manifest.json produces exactly
    # one runs row with a status -- never fewer (a silent drop) and never
    # more (a duplicate/double-count). Under --strict, additionally every
    # row must have left the "still running" ambiguity: pending is only a
    # valid status when the caller hasn't yet committed to "all workers are
    # done".
    invariant_holds = (n_rows == len(manifest_paths)) and (not strict or n_pending == 0)

    return {
        "n_manifests": len(manifest_paths),
        "n_reconciled": n_reconciled,
        "n_pending": n_pending,
        "n_harness_failure_missing_result": n_harness_failure_missing,
        "invariant_holds": invariant_holds,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    ap.add_argument("--db", default=str(DEFAULT_DB_PATH))
    ap.add_argument("--strict", action="store_true",
                     help="treat every unreconciled manifest as harness_failure "
                          "regardless of age (use once all campaign workers have exited)")
    args = ap.parse_args()

    summary = build_db(args.runs_dir, args.db, strict=args.strict)
    print(json.dumps(summary, indent=2))
    if summary["n_harness_failure_missing_result"] > 0:
        print(f"collector.py: {summary['n_harness_failure_missing_result']} run(s) had no "
              "result.json (attributed as harness_failure, not dropped)", file=sys.stderr)
    if not summary["invariant_holds"]:
        print("collector.py: reconciliation invariant violated", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
