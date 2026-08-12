# PROMPT.md — standing work order (worker iterations)

You are the implementation engineer for dcss-automation. Conventions and
guardrails are in `CLAUDE.md` and already loaded — follow them. This file is
the work order.

## Start of every session

1. Read `docs/JOURNAL.md`. The last **Next step** is where you begin.
2. Read `docs/BLOCKED.md` if it exists — skip blocked items, do the rest.
3. Check `logs/` for any long-running job you started previously and never
   collected the result of.

## The work

Execute `PLAN.md` §9 in order. You are done with a phase when its acceptance
tests pass — not when the work "looks finished".

### Phase 0 — Foundation and reconnaissance

Pin exact `crawl` + `qw` commits (§3). Build crawl with the `DGL_MILESTONES`
telemetry define (§6). Generate and archive the legal-character manifest and
weapon-option sets (§2). Measure per-game wall-clock/CPU/memory over ~50 mixed
games. Write the vendoring/patch-mechanism decision note. Verify `-list-combos`
on the pinned binary.

Exit — all of these must pass as tests, not existence checks:
- reproducible build from lock info on a clean machine;
- telemetry test asserts *exact expected* milestone/logfile records for a
  scripted short game;
- canary suite (GrBe + weapon-choice, zealot, caster, Felid, Mummy, Gnoll,
  Demigod, Formicid) each completing N decisions with no protocol error, hang,
  or unclassified prompt;
- sampler support-set diff vs. the executable's legal set is empty;
- throughput report exists and feeds Phase 1 sizing.

The commit-pin hunt is the fiddliest part of the whole project. Budget real
effort for it, and record what you tried in the journal so a fresh session does
not repeat dead ends.

### Phase 1 — Random-character fleet (core deliverable)

Sampler + per-game rc generation; god policy v0; runner state machine,
write-ahead accounting, progress-based hang detection (§6); collector +
outcome-vector report (§1) with stratified tables.

Exit: goodness-of-fit passes at campaign scale; forced-failure drills (induced
Lua error, `kill -9`, hang) each land in the correct terminal status with
artifacts attributed; parallel-isolation test with N workers shows zero
cross-contamination; the reconciliation invariant holds over a **≥500-game**
campaign with invalid-run rate <2%; the report reproduces byte-identically from
the SQLite DB.

**Running success for the project** = that ≥500-game campaign completing
unattended under the §2 randomness contract, with reconciled accounting and a
generated report committed to the repo.

### Phase 2 — Raise the floor

Per §8's experiment protocol. Each item is a hypothesis until measured, ships
behind a config flag, and is validated on held-out seeds.

## End of every session

Append a journal entry with an explicit **Next step**, then commit and push.
Leaving no trace is a failure — see `CLAUDE.md`.
