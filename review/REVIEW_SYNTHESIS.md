# Review synthesis

Stage 1 was completed without reading the author's review and committed as
`c2899f7`. This comparison uses that independent review, the subsequent reading
of `review/SELF_REVIEW.md`, the packet's verification ledger, and targeted
source spot-checks against `github.com/crawl/crawl` and
`github.com/crawl/qw`.

## Findings from the author that I confirm

- **H1, random-character contradiction — confirmed, but broader than stated.**
  The curated weapon default in `PLAN.md:273-278` directly contradicts the
  legal species × background × weapon goal in `PLAN.md:3-5`. The author is also
  right that the legal universe needs an executable validation step. However,
  validation against `-list-combos` covers only species/background pairs, not
  the weapon dimension.
- **H2, version inconsistency — confirmed.** The current/trunk inventory in
  `PLAN.md:70-76` cannot describe the population played by the proposed
  0.32-a0 qw/Crawl pair in `PLAN.md:166-171`. My upstream check also confirmed
  that public qw HEAD remains the July 2024 commit whose changelog identifies
  support for 0.32-a0. The exact compatible Crawl commit is still unspecified.
- **M1, unsupported Phase 2 targets — confirmed.** The absolute targets in
  `PLAN.md:244-245` have no baseline, sample size, or confidence requirement.
  Baseline-relative targets are better for planning, though they still need a
  minimum practically meaningful effect and a powered evaluation.
- **M2, seed limitations — confirmed with a technical correction below.**
  Common seeds are useful variance control, but different policies diverge and
  consume the random stream differently. They do not make resulting gameplay
  outcomes matched observations in the ordinary statistical sense.
- **M3, milestone source and partial-order issue — confirmed and upgraded.**
  The author correctly flags both the telemetry dependency
  (`PLAN.md:19-28`, `PLAN.md:153`, `PLAN.md:269-270`) and the invalid sequential
  interpretation of the milestone ladder. Source inspection turns the former
  from “unverified” into a concrete incompatibility: normal console builds do
  not write the milestone xlog; that write is behind `DGL_MILESTONES`, which
  Crawl 0.32.1 enables in its `DGAMELAUNCH` block.
- **M4, fleet failure handling — confirmed.** Progress-aware hang detection,
  stderr/message capture, unique directories/names, and an explicit
  resume-versus-abandon rule are required. These should be part of a complete
  run state machine and accounting model, not just operational conveniences.
- **M5, throughput budget — confirmed.** The “minutes” assertion in
  `PLAN.md:166-170` is not evidence for fleet sizing. Phase 0 should measure
  median/p95 elapsed time, CPU, memory, and failure latency before choosing
  concurrency and timeouts.
- **M6, caster share — confirmed.** The 40% estimate in `PLAN.md:232` should be
  computed from the pinned legal manifest and the definition of “caster,” then
  treated as a baseline descriptor rather than an assumption.
- **L1, current clua path is fair but undocumented — confirmed.** The verified
  clua accessors are player-knowledge-limited, so qw's current observation path
  does not inherently expose unseen monsters or unidentified item facts. The
  `c_persist`/reused-seed warning is valid, as is the rule that wizard runs
  cannot enter evaluation metrics.
- **L2, undocumented `-list-combos` — confirmed.** It is real but absent from
  help and should be pin-tested rather than treated as a stable documented
  contract (`PLAN.md:65`, `PLAN.md:291-292`).
- **L3 and L4, historical win rate and combo-count precision — confirmed.**
  Neither number is needed to justify the architecture. Qualify the historical
  statistic inline and obtain the legal count from the pinned executable.

## Findings I dispute, refine, or consider mis-prioritized

- **H1's proposed “uniform-over-legal-combos” contract is incomplete.** Crawl's
  native fully-random algorithm is not uniform over legal pairs: it randomly
  resolves species-first or background-first, then samples a compatible value
  in the other dimension. For weapon-choice backgrounds it also selects from
  the available weapon choices. The plan must first choose between emulating
  Crawl-native randomness and defining a new uniform distribution over legal
  triples. “Uniform legal combos” plus a curated weapon is neither. A universe
  diff alone tests support, not sampling probabilities.
- **M2's statement that `-seed` controls dungeon generation but not
  action/combat RNG is imprecise.** Seeded play fixes the initial pseudorandom
  state, including gameplay randomness, subject to the exact build and config.
  Once policies take different actions, they consume that state differently,
  so later draws no longer correspond. The edit should explain
  action-dependent stream divergence rather than imply combat randomness is
  unseeded.
- **M3's final-logfile fallback is insufficient for the promised report.** A
  final `place`, rune count, XL, and score cannot reconstruct whether optional
  Temple/Orc/branch events occurred, nor their ordering or maximum progress
  before a retreat. Either compile/test a milestone sink, capture equivalent
  events through an audited interface, or deliberately reduce the metric set
  to fields the final xlog can prove.
- **L1 is too low if fairness is an explicit acceptance dimension.** The
  present qw route is fair, but the architecture later adds LLM state exports,
  postmortems, repeated seeds, and potentially WebTiles (`PLAN.md:247-258`). A
  formal live-policy observation boundary and isolation tests belong in Phase
  0/1, even if future adapters are re-audited later.
- **L5, replacing submodules with shallow clones and a patch stack with a fork,
  is a repository preference, not a readiness correction.** An exact-commit
  submodule can improve reproducibility, while a shallow clone can complicate
  offline builds and historical commit availability. A fork can ease a large,
  long-lived divergence, but an overlay can make a small patch set auditable.
  Choose based on patch size, CI/cache needs, and update workflow; do not spend
  design time on this before the sampler, version pair, telemetry, and
  evaluation contract are fixed.

## Material findings the author missed

1. **No exact known-good version pair or compatibility gate.** Re-deriving the
   pool is necessary but does not prove that qw works on the selected Crawl
   revision. `PLAN.md:212-217` needs immutable Crawl/qw commits plus canaries
   covering representative prompt and species/background paths; one `GrBe`
   morgue is inadequate.
2. **The primary metric is not well-defined.** The author notices that the
   ladder is a partial order, but does not fully address “median milestone” in
   `PLAN.md:26-28`, optional Temple, variable branch order, or ambiguous
   cross-branch depth. Reports need independent monotone achievement indicators
   and a separately defined scalar/lexicographic optimization objective, if one
   is needed.
3. **The experiment protocol lacks holdout and provenance controls.** Beyond
   power, it needs a frozen `(character, seed)` manifest, both treatments on
   every manifest entry from clean state, an untouched evaluation set, effect
   sizes and uncertainty, declared invalid-run handling, and hashes for every
   executable, policy, patch, config, sampler, and schema. Reusing the same data
   to identify weak buckets and validate their fixes overfits the campaign.
4. **Run accounting and data integrity are unspecified.** Crashes and hangs may
   produce no final logfile row. The harness needs a write-ahead run manifest,
   unique run IDs, atomic ownership of artifacts, explicit terminal statuses,
   retry lineage, and reconciliation proving every scheduled run is accounted
   for exactly once.
5. **Wall-clock timeout is an evaluation confound.** In `PLAN.md:186-190`, a
   faster implementation gets more opportunity under the same elapsed-time
   cap, and host contention changes outcomes. Use turns/actions for evaluation
   budgets and a generous wall timeout only as an operational circuit breaker.
6. **The exits demonstrate output existence, not correctness.** A morgue and a
   report (`PLAN.md:212-227`) do not verify sampler probabilities, telemetry,
   parser correctness, deterministic replay, parallel isolation, forced
   crash/hang recovery, or completeness. Those need executable acceptance tests
   and a maximum invalid-run threshold.
7. **“One game = one process invocation” conflicts with resume.** The
   save-backup/resume language in `PLAN.md:186-190` and `PLAN.md:267-269` needs
   a state machine. It must define graceful checkpointing, whether live-save
   copying is valid, when a second process resumes a run, and whether resumed
   or restarted attempts enter metrics.
8. **Fairness must extend to future adapters and repeated-seed learning.** The
   author mentions `c_persist`, but the final contract should also prohibit a
   live policy from receiving the seed, raw saves, full-map/source internals,
   final telemetry, or knowledge from an earlier attempt at the same evaluation
   seed. WebTiles/LLM paths require a fresh audit.
9. **Optional layers are not harness-identical.** The artifact schema and
   reporting can be reusable, but WebTiles adds a server and a different
   lifecycle/transport/prompt path (`PLAN.md:136-142`, `PLAN.md:253-258`). A
   narrow player-adapter/run-result boundary is enough; the optional stack
   should not influence the core design before baseline readiness.

## Sufficiency of the author's edit list

The author's list is a strong start and correctly targets the two most visible
document contradictions. It is not sufficient for execution. In particular,
its randomness edit chooses an incomplete distribution, its milestone fallback
cannot reproduce the planned outcomes, its version edit does not identify and
test an exact compatible pair, and its A/B edit stops at seed semantics and
power. It also omits experiment holdout/provenance, terminal-state accounting,
wall-time bias, acceptance tests, and a corrected progress representation.

## Consolidated, deduplicated final edit list for `PLAN.md`

1. Define a precise **randomness contract**. Choose either Crawl-native
   fully-random chargen or a stated uniform distribution over legal
   species/background/weapon triples; define backgrounds without weapon
   choices, remove curated weapons from the “completely random” default, and
   treat curated weapons as a separately named experiment.
2. Generate and archive the legal character manifest from the pinned binary.
   Test both its support and the sampler's expected probabilities; pin-test the
   undocumented `-list-combos` helper but do not mistake its pair list for a
   weapon-complete universe.
3. State whether the product targets current DCSS or a historical qw-compatible
   release. Pin exact Crawl and qw commits, record their hashes in every run,
   correct the species/background claims to that version, and add representative
   compatibility canaries beyond `GrBe`.
4. Replace the assumed local `milestones` file with a concrete, source-backed
   telemetry design. Enable and test the necessary build/event path or reduce
   the promised metric set to final-xlog facts; make Phase 0 assert exact fields
   and events.
5. Replace the route-shaped milestone ladder with independent monotone outcomes:
   branch entry/end flags, rune count, Zot/Orb/win, XL, score, turns, and deepest
   level per branch. Define any scalar or lexicographic optimization objective
   explicitly and retain the full outcome vector.
6. Add a reproducible experiment protocol: frozen paired character/seed
   manifests, clean treatment isolation, a tuning/evaluation split with
   untouched holdout seeds, action-dependent RNG divergence caveats, power or
   precision targets, effect sizes and confidence intervals, declared invalid
   outcomes, and immutable build/policy/config/schema provenance.
7. Replace unsupported Phase 2 absolute gates with baseline-relative and
   minimum-practical-effect targets, each with a fixed sample size and
   uncertainty criterion. Treat “first win” as an event to report, not an exit
   condition.
8. Specify a runner state machine for win, death, intentional quit, stuck quit,
   Lua error, crash, wall timeout, invalid telemetry, and harness failure.
   Define graceful stop, checkpoint validity, resume/restart and retry lineage,
   terminal metric eligibility, per-run names/directories, and captured
   stderr/message artifacts.
9. Add write-ahead run IDs/manifests and scheduled-to-terminal reconciliation so
   missing final xlog rows cannot silently exclude failures or double-count
   retries. Use turn/action budgets for evaluation and wall time only as a
   generous operational circuit breaker.
10. Strengthen Phase 0/1 exits with automated tests for sampler support and
    distribution, seeded replay, telemetry/parser fixtures, parallel isolation,
    forced Lua error/crash/hang recovery, artifact attribution, report
    invariants, and a specified maximum invalid-run rate. Measure median/p95
    wall time, CPU, memory, and failure-detection latency before sizing campaigns.
11. Add an enforceable fairness contract: live policies receive only audited
    player-knowable observations; wizard runs never enter metrics; seeds, raw
    saves, source/full-map internals, final logs, and prior attempts at the same
    evaluation seed cannot reach the policy; cross-game persistence is cleared
    for controlled tests; each future WebTiles/LLM adapter is re-audited.
12. Compute caster share and other pool statistics from the pinned manifest,
    qualify historical win/throughput claims inline, and label expected Phase 2
    benefits as hypotheses. Defer optional WebTiles/LLM/own-bot detail, exposing
    only a small player-adapter/run-result boundary for future reuse.
