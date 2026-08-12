# dcss-automation

Dungeon Crawl Stone Soup — automated player logic.

**Goal:** start DCSS, roll a random character under a precisely defined
distribution, and play it autonomously as far into the game as possible,
repeatedly and measurably.

## Canonical plan

**[`PLAN.md`](PLAN.md)** is the canonical, execution-ready plan (revision 2,
independently reviewed). Architecture in one line: a Python harness (game
lifecycle, character sampling, telemetry, reports) around a pinned local
crawl build, with the [qw bot](https://github.com/crawl/qw) as the
in-process player engine via crawl's embedded Lua (clua).

Implementation starts at **`PLAN.md` §9, Phase 0**, which is a
self-contained work order with acceptance-test exit criteria.

## Supporting documents

- [`review/`](review/) — the plan's full review trail:
  [`REVIEW_PACKET.md`](review/REVIEW_PACKET.md) (review task + verification
  ledger), [`SELF_REVIEW.md`](review/SELF_REVIEW.md) (author findings),
  [`INDEPENDENT_REVIEW.md`](review/INDEPENDENT_REVIEW.md) and
  [`REVIEW_SYNTHESIS.md`](review/REVIEW_SYNTHESIS.md) (independent reviewer;
  their consolidated edit list produced plan v2).
- [`reference/`](reference/) — **not the plan of record**:
  [`AUTOMATION_PLAN.md`](reference/AUTOMATION_PLAN.md), an alternate plan
  from a separate agent session (custom source-adapter architecture), kept
  for its strong engineering-methodology sections, plus
  [`AUTOMATION_PLAN_REVIEW.md`](reference/AUTOMATION_PLAN_REVIEW.md), the
  independent review of it explaining why the qw-based plan was preferred.

## Autonomous operation

This repo is developed by an unattended agent loop. Live state is
[`docs/JOURNAL.md`](docs/JOURNAL.md) — read its last **Next step** to see where
work stands.

- [`CLAUDE.md`](CLAUDE.md) — operating conventions and guardrails (auto-loaded)
- [`PROMPT.md`](PROMPT.md) — standing work order for worker iterations
- [`ORCHESTRATOR.md`](ORCHESTRATOR.md) — periodic strong-model review pass
- [`ops/supervise.sh`](ops/supervise.sh) — the restart loop;
  [`ops/config.env`](ops/config.env) tunes models and brakes
- [`docs/decisions/`](docs/decisions/) — one file per decision made without a human

Runtime is an isolated WSL2 distro (`dcss-agent`). Start with
`ops/supervise.sh`; stop it with `touch ops/STOP`.

## Status

Planning complete; autonomous runtime provisioned. Next milestone: Phase 0 (pin
crawl+qw commits, build with telemetry, generate the legal-character manifest,
run compatibility canaries, measure throughput) — see `PLAN.md` §9 for the exit
criteria.
