# Independent review of `PLAN.md`

## Findings, ordered by severity

### High — The default sampler does not implement the stated “completely random” character

`PLAN.md:3-5` defines the population as any legal species × background ×
weapon, but the recommended implementation samples a species/background entry
uniformly from `-list-combos` and then assigns a *sensible* weapon
(`PLAN.md:65-68`, `PLAN.md:173-180`, `PLAN.md:220-221`,
`PLAN.md:273-278`). `-list-combos` enumerates species/background pairs, not
legal triples, and `hypercombogen.sh` deliberately chooses weapons by curated
rules. Thus the default gives probability zero to most legal starting-weapon
alternatives and is neither uniform over legal triples nor equivalent to
Crawl's native `fully_random` distribution.

This is not resolved by choosing “uniform over combos” in `PLAN.md:273-275`.
In Crawl 0.32 source, native fully-random chargen randomly chooses whether to
resolve species or background first, samples that dimension uniformly, then
samples a compatible value in the other dimension; it subsequently samples
uniformly among the available weapons for backgrounds that offer a weapon
choice. That distribution is generally not uniform over compatible
species/background pairs. “Unbiased” therefore has no answer until the plan
defines its target distribution. If the goal means Crawl-native random, the
harness should invoke or faithfully reproduce and test that distribution. If
the goal means uniform over legal triples, it must enumerate legal weapon
choices and specify how triples for backgrounds without a weapon choice are
represented.

### High — The proposed console build does not provide one of the collector's ground-truth inputs

The plan says Crawl natively writes morgues, `logfile`, and `milestones`
(`PLAN.md:26-28`), chooses a console/headless build (`PLAN.md:157-172`), and
makes milestone parsing central to Phase 1 (`PLAN.md:223-227`,
`PLAN.md:269-270`). A source spot-check of Crawl 0.32.1 contradicts this
combination: `mark_milestone` writes the `milestones` xlog only when
`DGL_MILESTONES` is compiled, and `AppHdr.h` enables that define inside the
`DGAMELAUNCH` block. A normal local console build does not produce that file.
`USE_TILE_WEB` sends milestone events to WebTiles, but does not by itself write
the xlog file.

This breaks the stated collector and progress report on the recommended build.
Phase 0 must select and prove a concrete telemetry path: build with the
required define, add a player-knowledge-safe event sink, consume WebTiles
events, or derive a deliberately smaller set of outcomes from the final
logfile. The smoke test must assert exact expected records and fields, not only
that a morgue appeared.

### High — The supported game and character population are internally inconsistent

The research summary describes the 0.34/trunk species/background population
(`PLAN.md:70-76`), while the player is qw master, documented as supporting
0.32-a0 (`PLAN.md:94-95`, `PLAN.md:166-171`, `PLAN.md:266`). The ledger already
notes that the two populations differ. My network spot-check confirmed that
qw's current public HEAD is still the July 2024 commit whose changelog says
“supports DCSS 0.32-a0”; that is not an exact Crawl revision. “Vendor qw at the
matching tag” (`PLAN.md:212-217`) consequently does not identify a reproducible
pair, and a successful `GrBe` smoke test would not establish broad compatibility
with random combos.

The plan must decide whether the product targets a historical version that qw
can play or the current game. It should pin immutable commits and record the
legal population emitted by that exact executable. Phase 0 should verify a
known-compatible pair and run canaries covering weapon prompts, zealots,
casters, and restrictive species. Saying that being a version behind “costs
nothing” (`PLAN.md:264-266`) is incorrect if “all legal characters” is meant
for current DCSS.

### High — The evaluation design cannot yet support its improvement claims

A 500–1,000-game campaign (`PLAN.md:225-227`) is enough for an integration
burn-in, but not automatically enough for the promised per-species/background
comparisons across hundreds of combos (`PLAN.md:26-28`) or for detecting modest
policy changes. The A/B statement (`PLAN.md:242-243`) specifies common seeds
but no experimental unit, pairing rule, sample-size/power calculation,
confidence interval, treatment of crashes/timeouts, multiple-comparison policy,
or separation of tuning data from evaluation data. “Same seeds” does not make
two trajectories identical after policies choose different actions and consume
the random stream differently; it is useful variance control, not a substitute
for statistical analysis. Repeatedly targeting the worst observed buckets on
the same campaign also overfits the benchmark.

Define a frozen run manifest of `(combo/triple, seed)` pairs, run both policies
on every pair from clean state, retain an untouched holdout set, report effect
sizes and uncertainty for predeclared primary outcomes, and predefine how
non-game-ending outcomes are counted. Record executable, qw, patch, config,
sampler, schema, and run-manifest hashes. The Phase 2 thresholds
(`PLAN.md:244-245`) need a sample size and confidence criterion; “first win
observed” is a useful event, not a reliable exit gate.

### Medium — The primary milestone ladder is not a valid total ordering of DCSS progress

The ladder in `PLAN.md:19-24` imposes a single route on events that are optional
or can occur in different orders. Temple can be skipped, Orc and Lair ordering
can vary, branch selection varies, and rune/branch progress is not captured by
one monotone label. Taking a “median milestone” over that ordering
(`PLAN.md:26-28`) can rank route choice rather than actual progress. “Max
dungeon depth” is also ambiguous: numeric depth across branches is not directly
comparable.

Represent achievements as independent monotone indicators (branch entered,
branch end reached, rune count, Zot/Orb/win), plus XL, turns, score, and deepest
level per branch. If a scalar objective is required for tuning, define and
justify its exact lexicographic or weighted ordering before experiments. Keep
the full outcome vector in reports rather than treating one canonical route as
ground truth.

### Medium — Timeout, save, retry, and terminal-state semantics are underspecified and partly contradictory

“One game = one process invocation” conflicts with “save-backup” and
“resume-or-abandon” (`PLAN.md:186-190`, `PLAN.md:267-269`). Copying a live save
is not necessarily an atomic or valid checkpoint, a hard wall-clock kill can
occur between saves, and resuming requires another invocation. A wall-clock
cutoff also makes policy speed and host load affect game outcomes, contaminating
A/B results.

Specify a state machine with terminal statuses such as win, death, intentional
quit, stuck-turn quit, crash, wall timeout, invalid telemetry, and harness
failure. Define graceful-stop behavior, checkpoint ownership, retry limits,
whether retries resume or restart, and exactly which statuses enter gameplay
metrics. Use in-game turns/actions for experimental budgets; retain wall time
only as a generous fleet safety bound. Use per-run directories and a
write-ahead manifest so crashed games, which may have no final logfile row, are
still attributable and are never silently dropped or double-counted.

### Medium — The phase exits test artifact existence, not correctness

Phase 0 exits when one favored combo produces a morgue (`PLAN.md:212-217`), and
Phase 1 exits when a campaign produces a report (`PLAN.md:219-227`). Neither
checks sampler distribution, prompt coverage, version identity, telemetry
completeness, isolation under parallelism, restart behavior, or collector
accuracy. A report can look complete while excluding every crash or
misclassifying milestones.

Add automated acceptance tests: sampler support and goodness-of-fit (or exact
manifest validation), seeded determinism/replay checks, fixture-based xlog
parsing, unique run IDs, reconciliation of scheduled versus terminal runs,
parallel isolation, forced crash/hang recovery, and a report invariant that
accounts for every scheduled run. Make Phase 1's exit a fixed campaign with a
specified maximum invalid-run rate and successful reconciliation, not merely a
range of game counts.

### Medium — The current observation path appears fair, but fairness is not an enforceable architecture invariant

The verified clua APIs described in `PLAN.md:44-52` gate monster visibility and
item identification to player-known state, so the qw-in-clua backbone in
`PLAN.md:157-162` does not inherently leak hidden information. That is the
right default. The plan nevertheless never states an observation contract, and
the later LLM export/offline loop (`PLAN.md:247-252`) creates new paths by
which a seed, morgue, full map, prior replay of the same seed, or postmortem
knowledge could reach a live policy.

Declare that an in-game policy may receive only state exposed through the
player-knowledge-limited clua surface (or an explicitly audited equivalent).
Keep seed, source internals, raw save data, final logs, and prior attempts at a
test seed outside the live policy boundary. Make telemetry read-only during a
run, isolate cross-game persistence for paired tests, and add probes for unseen
monsters and unidentified items. Re-audit the boundary before enabling any
WebTiles or LLM player path.

### Low — Several quantitative claims should be labeled as hypotheses, not planning inputs

The historical win-rate and 15-rune statements (`PLAN.md:30-33`,
`PLAN.md:80-95`), “games in minutes” throughput claim
(`PLAN.md:166-170`), caster share and “Magic Dart until Lair” benefit
(`PLAN.md:229-235`), and external LLM comparisons (`PLAN.md:103-110`) are not
all primary-source verified. None is needed to justify the sensible decision
to start from qw. Remove exact numbers that cannot be sourced, cite and date
the rest, and relabel expected Phase 2 results as hypotheses to be measured.
Benchmark throughput in Phase 0 before choosing fleet size or timeout values.

### Low — Optional architecture is presented as more reusable than it is

The claim that the Phase 1 harness remains “identical” for a later WebTiles bot
(`PLAN.md:136-142`, `PLAN.md:253-258`) is too strong: artifact schema and
reporting can remain stable, but process lifecycle, server management,
observation/action transport, prompt handling, and test tooling will change.
Define a small player-adapter/run-result interface if this future portability
matters. Otherwise defer WebTiles, LLM, and own-bot design until the symbolic
baseline is trustworthy; they are not needed for the core deliverable.

## Suggested focused edits

1. Rewrite the goal and randomization section around one explicit probability
   distribution: Crawl-native fully random or uniform legal triples. Make the
   default weapon policy conform to it, and describe curated weapons as a
   separately named treatment rather than “completely random.”
2. Choose the supported Crawl version, pin exact Crawl and qw commits, generate
   and archive the legal-character manifest from that executable, and add a
   representative compatibility canary suite to Phase 0.
3. Replace the assumption about local `milestones` with a tested telemetry
   design and update the build flags, collector, and Phase 0 exit criterion
   accordingly.
4. Replace the route-shaped milestone scalar with a vector of monotone outcome
   indicators; define the primary optimization metric and all branch/depth
   semantics precisely.
5. Add an experiment protocol covering frozen paired manifests, independent
   holdout seeds, sample size, uncertainty, exclusions, invalid outcomes, and
   immutable version/config hashes.
6. Specify the runner state machine, per-run isolation, graceful termination,
   checkpoint/retry policy, and scheduled-to-terminal reconciliation.
7. Turn Phase 0/1 exits into acceptance criteria with sampler, telemetry,
   parser, determinism, parallelism, crash/hang, and completeness tests. Give
   Phase 2 targets sample sizes and confidence bounds.
8. Add an explicit observation-fairness boundary and tests, including rules
   preventing seeds and postmortem knowledge from reaching a live policy or a
   later attempt on the same evaluation seed.
9. Move unsupported performance/history assertions and Phase 2 expectations
   into dated evidence or clearly labeled hypotheses, and defer optional
   WebTiles/LLM detail until the baseline meets its exits.

## Execution-readiness verdict

**Not ready to execute as written.** The high-level choice—pinned local Crawl,
qw as the in-process symbolic player, and an external lifecycle/metrics
harness—is technically feasible and is the shortest credible route to deep
runs. The current clua observation interface is also fair based on the verified
source surface. However, the default character distribution contradicts the
goal, the recommended build does not emit the assumed milestone file, the
Crawl/qw version pair and population are unresolved, and the evaluation
protocol cannot yet establish improvement. Resolve those four items before
implementation; the remaining medium findings should become Phase 0/1
acceptance criteria rather than deferred cleanup.
