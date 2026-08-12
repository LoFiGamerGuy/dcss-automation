# 010 — Turn budget for the Phase 1 ≥500-game campaign

## Context

PLAN.md §6 requires the per-run cap to be a turn/action budget
(`timeout_turns`), not wall-clock, because wall-clock ties policy speed and
host load to game outcomes. Choosing that number needs a distribution of
`turns_survived` from natural-ending games (`died`/`quit_stuck`) to pick a
cutoff that rarely truncates a real outcome.

Two prior pilot attempts (this session and the one before) were spent on
environment survivability (`nohup` alone didn't survive a session boundary;
`setsid nohup ... & disown` did — see docs/JOURNAL.md 2026-08-12) and on a
relative-workdir contamination bug (fixed in 642e3ec), not on this
statistic. A third pilot (`--n-games 40 --workers 10 --turn-budget 0
--wall-cap-secs 900`, prefix `pilot-turns`, char_seed 0-39) finally ran
clean: 40/40 reconciled, zero contamination (40 unique char_seeds, manifest
run_id matches dir name for all), collector invariant holds.

## Data

Pilot outcome mix (n=40): 32 `died`, 4 `lua_error`, 2 `quit_stuck` (qw's own
QUIT_TURNS stuck detection, at turn 8000/9000), 2 `timeout_wall` (both were
the 120s progress-hang path, not the 900s wall cap — no run in this pilot
hit the literal wall cap).

`lua_error` is a real, distinctly-classified terminal status (PLAN.md §6),
not a harness defect — it does not count against the <2% invalid-run-rate
target, which applies to `invalid_telemetry`/`harness_failure` (protocol
failures). Not investigated further here; if its rate holds at campaign
scale it's a Phase-2-relevant qw/crawl-dev-build finding, not a Phase 1
blocker.

`turns_survived` over the 34 natural-end runs (`died` + `quit_stuck`):

| stat | value |
|---|---|
| n | 34 |
| median | 1015 |
| p95 | 9595 |
| max | 11794 |

Turns-per-second is not constant: early game (turn <200) runs ~15-25
turns/s, later game (turn >5000) runs 200-600 turns/s (qw's travel/rest
auto-fast-forwards many turns per real second once past early exploration).
So a generous turn cap is cheap in wall-clock — the pilot's single longest
natural run (11794 turns) still finished in 25s wall.

## Decision

**`--turn-budget 20000`** for the Phase 1 ≥500-game campaign.

That's ~2.1x the pilot's p95 and ~1.7x its observed max, on only 34
samples — deliberately generous rather than a tight percentile fit, since
undercounting is worse here than a few extra idle seconds per truncated
run: an over-tight budget would misclassify real deaths/quits as
`timeout_turns` and bias the outcome-vector report. Given the
turns/s-accelerates-with-depth pattern above, 20000 turns costs at most tens
of seconds of wall-clock even for outlier survivors, so there's no
throughput reason to tighten it.

`--wall-cap-secs 900` (existing default, matches the Phase 0 throughput
probe's safety cap) and `--hang-secs 120` (existing default) are kept
unchanged as the operational circuit breakers under the turn budget.

## Revisit

This is a first cut from a 40-game pilot, not the final campaign. If the
500-game campaign's own `timeout_turns` rate turns out non-trivial (i.e.
20000 is truncating a meaningful share of natural runs, visible as a
turns_survived distribution piling up near the cap), revisit before Phase 2
uses this campaign as its baseline.
