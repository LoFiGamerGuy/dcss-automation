#!/usr/bin/env python3
"""Phase 1 outcome-vector report (PLAN.md §1): reads a SQLite DB built by
ops/collector.py and produces the stratified report -- terminal-status
distribution, rune/orb/win rates, XL/score/turn percentiles, and per-branch
entered/branch-end-reached rates -- broken out overall and by each of
species/background/archetype (§1: "Reports keep the full vector, stratified
by species, background, and archetype").

Deliberately a pure function of the DB contents only (`generate(db_path)`
takes no wall-clock input, sorts every dict/list it emits, and the CLI's
JSON dump uses sort_keys=True): Phase 1's exit criterion is that "the report
reproduces byte-identically from the SQLite DB" -- rerunning this against an
unchanged DB must produce byte-identical output, not just equivalent data in
a different key order.

Per-branch entered/branch-end-reached indicators come from the milestones
table's `br.enter`/`br.end` records (mark_milestone call sites in
crawl-ref/source/*.cc), not from the single final logfile row, which only
carries the *last* place a run was in, not its full branch history.

Library use: `generate(db_path) -> dict`.
CLI use: `report.py --db PATH [--out PATH]` (prints to stdout if --out
omitted).
"""
import argparse
import json
import pathlib
import sqlite3
import sys

TERMINAL_STATUSES = [
    "won", "died", "quit_intentional", "quit_stuck", "lua_error", "crashed",
    "timeout_turns", "timeout_wall", "invalid_telemetry", "harness_failure",
    "pending",
]


def _percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _numeric_stats(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {"n": 0, "median": None, "p95": None, "min": None, "max": None}
    return {
        "n": len(vals),
        "median": _percentile(vals, 0.5),
        "p95": _percentile(vals, 0.95),
        "min": vals[0],
        "max": vals[-1],
    }


def _bucket(conn, where_sql, params):
    rows = conn.execute(
        f"SELECT run_id, status, xl, sc, turn, urune, killer FROM runs WHERE {where_sql}",
        params,
    ).fetchall()
    n = len(rows)
    status_counts = {s: 0 for s in TERMINAL_STATUSES}
    for r in rows:
        status_counts[r[1]] = status_counts.get(r[1], 0) + 1

    run_ids = [r[0] for r in rows]
    branch_rows = []
    if run_ids:
        placeholders = ",".join("?" for _ in run_ids)
        branch_rows = conn.execute(
            f"SELECT run_id, type, br FROM milestones "
            f"WHERE run_id IN ({placeholders}) AND type IN ('br.enter','br.end')",
            run_ids,
        ).fetchall()
    entered_by_branch = {}
    ended_by_branch = {}
    for run_id, mtype, br in branch_rows:
        target = entered_by_branch if mtype == "br.enter" else ended_by_branch
        target.setdefault(br, set()).add(run_id)

    all_branches = sorted(set(entered_by_branch) | set(ended_by_branch))
    branch_table = {
        br: {
            "entered_n": len(entered_by_branch.get(br, ())),
            "entered_rate": len(entered_by_branch.get(br, ())) / n if n else None,
            "end_reached_n": len(ended_by_branch.get(br, ())),
            "end_reached_rate": len(ended_by_branch.get(br, ())) / n if n else None,
        }
        for br in all_branches
    }

    rune_runs = [r for r in rows if (r[5] or 0) > 0]
    death_causes = {}
    for r in rows:
        if r[1] == "died" and r[6]:
            death_causes[r[6]] = death_causes.get(r[6], 0) + 1

    return {
        "n": n,
        "status_counts": status_counts,
        "win_rate": status_counts["won"] / n if n else None,
        "rune_rate": len(rune_runs) / n if n else None,
        "rune_count_distribution": _distribution([r[5] or 0 for r in rows]),
        "xl": _numeric_stats(r[2] for r in rows),
        "score": _numeric_stats(r[3] for r in rows),
        "turns_survived": _numeric_stats(r[4] for r in rows),
        "branches": branch_table,
        "death_causes": dict(sorted(death_causes.items())),
    }


def _distribution(values):
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return {str(k): counts[k] for k in sorted(counts)}


def generate(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        overall = _bucket(conn, "1=1", [])

        by_species = {}
        for (species,) in conn.execute("SELECT DISTINCT species FROM runs ORDER BY species"):
            by_species[species] = _bucket(conn, "species = ?", [species])

        by_background = {}
        for (background,) in conn.execute("SELECT DISTINCT background FROM runs ORDER BY background"):
            by_background[background] = _bucket(conn, "background = ?", [background])

        by_archetype = {}
        for (archetype,) in conn.execute("SELECT DISTINCT archetype FROM runs ORDER BY archetype"):
            by_archetype[archetype] = _bucket(conn, "archetype = ?", [archetype])

        return {
            "overall": overall,
            "by_species": by_species,
            "by_background": by_background,
            "by_archetype": by_archetype,
        }
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", help="write JSON here instead of stdout")
    args = ap.parse_args()

    if not pathlib.Path(args.db).exists():
        print(f"report.py: {args.db} not found; run ops/collector.py first", file=sys.stderr)
        sys.exit(1)

    report = generate(args.db)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
