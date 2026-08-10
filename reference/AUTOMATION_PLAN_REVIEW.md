# Objective review of `AUTOMATION_PLAN.md`

## Executive assessment

This is a thoughtful experimental-platform plan with unusually good attention
to reproducibility, process isolation, observation fairness, artifact
provenance, and delayed use of machine learning. Its layered player design and
test pyramid are directionally sound.

It is **not execution-ready as written**, principally because it selects a
large custom C++ adapter before accurately evaluating DCSS's existing
structured interfaces, understates the adapter and game-playing effort, and
does not yet define an evaluation or randomization contract tightly enough to
support the claimed results. The best next step is an interface and baseline
spike, not immediate implementation of the proposed architecture.

## Findings, ordered by severity

### High — The core interface recommendation is based on an inaccurate alternatives analysis

The plan commits to a patched source adapter (`AUTOMATION_PLAN.md:25-34`,
`AUTOMATION_PLAN.md:38-55`) and dismisses WebTiles as browser automation with
DOM/canvas extraction (`AUTOMATION_PLAN.md:66-71`). That description is
incorrect. DCSS WebTiles exposes a direct structured JSON/WebSocket protocol;
an agent does not need to automate a browser. Crawl also already has clua
modules for structured, player-knowledge-limited state and command injection,
and [qw](https://github.com/crawl/qw) demonstrates that clua can support a
full autonomous player. See the upstream
[WebTiles implementation](https://github.com/crawl/crawl/blob/master/crawl-ref/source/tileweb.cc),
[webserver](https://github.com/crawl/crawl/tree/master/crawl-ref/source/webserver),
and [clua command surface](https://github.com/crawl/crawl/blob/master/crawl-ref/source/l-crawl.cc).

A C++ adapter could ultimately offer cleaner semantic actions, stronger
instrumentation, and controlled scenarios, but it imposes the highest
maintenance burden and creates a modified game whose equivalence to normal
play must continually be proved. Phase 0 should compare clua, direct WebTiles,
and a minimal source patch against explicit requirements: observation
coverage, prompt handling, fairness, action granularity, throughput, replay,
version coupling, and maintenance cost. The architecture decision should be
the output of that spike, not its starting assumption.

The plan also omits qw from its prior-art and baseline analysis. If the actual
goal is to get random characters “as far as possible,” discarding the strongest
available player and rebuilding tactics from scratch is a major opportunity
cost. Either adopt/extend qw, use it as an evaluation baseline, or explicitly
state that the project's primary goal is a new research platform rather than
the fastest route to deep DCSS runs.

### High — The adapter scope and delivery estimates are not credible without a much narrower vertical slice

The proposed interface covers map knowledge, inventory identity, monsters,
skills, spells, gods, prompts, targeting, legal actions, travel, exclusions,
save/resume, replay, and semantic command translation
(`AUTOMATION_PLAN.md:117-166`). Phase 2 assigns one to two weeks to implement
that surface and then claims that 10,000 random actions can establish no crash,
leak, deadlock, or unclassified prompt (`AUTOMATION_PLAN.md:349-356`). Phase 3
then assigns two to four weeks to a baseline covering exploration, equipment,
melee, ranged attacks, spells, retreat, consumables, and skill development for
every valid start (`AUTOMATION_PLAN.md:358-365`). DCSS's rare prompt and rules
surface makes both estimates highly optimistic.

The process integration is not specified at the point where feasibility
depends on it. A console build already owns stdin/stdout for its terminal UI,
so the suggested length-prefixed protocol over those streams
(`AUTOMATION_PLAN.md:119-122`) cannot simply coexist with curses/PTY traffic.
Use a Unix socket or dedicated inherited file descriptors, or define an adapter
mode that disables the normal terminal and explain how its behavior is checked
against normal play. Specify exactly where the game pauses for an agent
decision, how prompts are surfaced, and whether one protocol step means one
input, one player action, or possibly many turns.

Reduce Phase 2 to a measured vertical slice: a small observation schema,
movement/wait/prompt actions, a dedicated transport, and one visibility
noninterference suite. Expand only after comparing it with clua and WebTiles.
Treat timeline estimates after that point as evidence-dependent ranges.

### High — Evaluation is statistically principled in tone but underspecified in the places that determine validity

The plan names win rate over a fixed hidden seed set as the primary score
(`AUTOMATION_PLAN.md:13-16`) and later proposes development, validation, and
hidden evaluation seeds (`AUTOMATION_PLAN.md:294-315`). Win rate will be zero
for most early policies and therefore cannot guide Phase 3. A fixed local
“hidden” set is also only hidden by convention, becomes overfit through
repeated release evaluations, and estimates performance conditional on that
particular set rather than the target random-game distribution.

The experimental unit is a complete `(game version, character draw, game
seed)` manifest, not only a game seed. Comparisons need frozen manifests,
paired policy runs from clean state, independent freshly sampled holdout
manifests or genuinely sequestered one-use test sets, declared treatment of
timeouts/crashes/saves, effect sizes, confidence intervals, and minimum
practically meaningful changes. Updating DCSS versions changes generation and
rules, so results must not be pooled across versions as if directly paired.

Several secondary metrics also need correction. “Deepest dungeon level” is
ambiguous across branches; turns survived can reward stalling; and milestone
completion is a partial outcome vector rather than a single ordered value
(`AUTOMATION_PLAN.md:15-16`, `AUTOMATION_PLAN.md:298-306`). Define branch
entry/end indicators, rune count, Zot/Orb/win, XL, score, and deepest level per
branch. Use a predeclared early-game composite or milestone vector while wins
are absent. Compare Phase 3 to qw and the previous released policy, not merely
to a random-action baseline (`AUTOMATION_PLAN.md:364-365`), which is too weak to
show useful competence.

### High — “Random character” still lacks one internally consistent probability distribution

The plan improves on vague randomness by choosing uniform valid
species/background pairs (`AUTOMATION_PLAN.md:168-186`), but step 3 permits
either the game's normal random resolution of subchoices or external uniform
enumeration (`AUTOMATION_PLAN.md:177-178`). Those can produce different
distributions. Uniform pairs followed by uniform weapon choice is also not
uniform over legal species/background/weapon triples, while neither necessarily
matches Crawl's native fully-random algorithm.

There is also a direct tension between letting the game randomize subchoices
and keeping character RNG separate from game RNG (`AUTOMATION_PLAN.md:177-184`).
If chargen consumes the game's RNG stream, the chosen subchoice can alter later
random-stream consumption unless the pinned source proves separate streams.

Choose and name one target distribution: Crawl-native fully random, uniform
legal pairs plus a specified conditional subchoice distribution, or uniform
legal triples. Generate a canonical full candidate manifest from the pinned
binary, define no-choice backgrounds, specify the exact RNG and unbiased index
sampling method, and validate exact support as well as empirical frequencies.
The run manifest should record the fully resolved character and keep all
character-selection seeds inaccessible to the live policy.

### High — The observation allowlist contains fields that can leak more than the normal player interface

The plan correctly recognizes hidden-information risk
(`AUTOMATION_PLAN.md:47-55`, `AUTOMATION_PLAN.md:124-146`), but an allowlist of
fields is not sufficient when values are serialized from privileged game
objects. Particular hazards include:

- a persistent “agent-maintained” monster ID that allows identical monsters to
  be recognized after leaving sight (`AUTOMATION_PLAN.md:137-138`);
- a legal-action mask whose legality or target list is derived from hidden
  identities, unseen entities, or internal command preconditions
  (`AUTOMATION_PLAN.md:139-142`);
- “result/cost of the previous action” if it exposes exact damage, monster HP,
  random rolls, or effects the UI only describes approximately
  (`AUTOMATION_PLAN.md:139-140`); and
- remembered-cell contents or staleness calculated from current hidden state
  rather than the player's map memory (`AUTOMATION_PLAN.md:135-136`).

Serialize through the game's player-knowledge/view model wherever possible,
not by reading raw state and filtering fields afterward. Define whether entity
IDs are step-scoped or may persist only while continuity is player-observable.
Legal masks must be a pure function of the disclosed observation and public
rules. Training may use privileged labels offline, but production model inputs
must remain identical to the audited observation contract.

The proposed test “hidden fields cannot affect serialized observations”
(`AUTOMATION_PLAN.md:144-146`) needs a precise noninterference construction:
paired game states with identical player-knowable projections but varied hidden
state must serialize identically. PTY differential tests are useful but cannot
prove this alone, because a single terminal screen does not contain everything
a player can inspect through menus. Also isolate manifests, game seeds, raw
saves, full event logs, and prior attempts on an evaluation seed from the live
policy process.

### Medium — Semantic-action atomicity conflicts with per-turn tactical safety

`Rest`, `AutoExplore`, and `TravelTo` may execute multiple turns
(`AUTOMATION_PLAN.md:152-166`), while tactics are described as running on every
decision (`AUTOMATION_PLAN.md:209-226`) and navigation initially requires
reevaluation every turn (`AUTOMATION_PLAN.md:228-235`). The protocol does not
say whether native automation yields an observation at each interrupt/turn,
whether the safety controller can veto continuation, or how replay counts a
partially completed action.

Define the atomicity contract. A safe first version should execute at most one
turn-consuming player action per `step_id`; travel/rest can be policy-side
macros resubmitted after each observation. If native multi-turn commands remain,
model them as interruptible sessions with child events, explicit stop reasons,
and deterministic replay semantics.

The action union is also not yet a complete protocol: shopping, spell
memorization/forgetting, religion transitions, item-specific menus, map/look
screens, and version-specific prompts need either semantic variants or a
strictly bounded generic prompt mechanism. Item and target IDs should be scoped
to the observation that issued them so stale actions fail deterministically.

### Medium — The telemetry artifact assumes milestone data that a normal console build does not emit

The run layout promises `game.log` with messages and milestones
(`AUTOMATION_PLAN.md:277-287`). In Crawl 0.32.1, the milestone xlog write is
compiled behind `DGL_MILESTONES`, enabled within the `DGAMELAUNCH` block; a
plain local console build does not natively produce that file. The custom
adapter could emit equivalent player-known progress events, but the plan must
say so and define their schema. Phase 0 should prove the selected telemetry
path and reconcile every scheduled run even when a crash produces no final
score/logfile row.

### Medium — Terminal-state, retry, and evaluation eligibility rules remain incomplete

The safety layer is stronger than most plans (`AUTOMATION_PLAN.md:190-200`),
but “saved” is listed as terminal without defining whether it is resumed, and
per-run deadlines can censor slow policies or convert imminent failures into
saves. Missing statuses include intentional policy quit, stuck/no-progress
abort, invalid telemetry, and harness failure. Retry attempts need parent/child
lineage and a rule preventing double counting.

Use turn/action limits for experimental budgets and a generous wall-clock
watchdog only as an operational circuit breaker. Define graceful checkpoint
semantics, retry limits, resume-versus-restart policy, metric eligibility for
each status, and scheduled-to-terminal reconciliation by `run_id`. CPU time can
still be reported as an efficiency metric without determining how long a game
is allowed to play.

### Medium — The phase exits do not demonstrate the guarantees they claim

One hundred fixed-length starts (`AUTOMATION_PLAN.md:341-347`) exercise setup
but not the prompt/state space. Ten thousand random legal actions
(`AUTOMATION_PLAN.md:349-356`) will concentrate on common early states and
cannot prove absence of information leaks or unclassified rare prompts. A
random-action comparison in Phase 3 can be passed by a minimally competent
agent without demonstrating meaningful progress (`AUTOMATION_PLAN.md:358-365`).

Replace raw action counts with coverage and invariants: every known protocol
mode and action variant exercised; scenario fixtures for rare prompts;
coverage-guided/fuzzed transition sequences; paired hidden-state
noninterference tests; forced disconnect, crash, timeout, save, and resume;
artifact reconciliation; and a soak-test invalid-run ceiling. Phase 3 should
beat qw or a stated competent heuristic on predeclared held-out outcomes, or at
minimum reach absolute gameplay milestones with uncertainty bounds.

### Medium — Replay and conformance need a clearer authority model

Observation-hash replay is valuable (`AUTOMATION_PLAN.md:275-292`), but the plan
does not distinguish three different guarantees:

1. protocol replay, which replays recorded observations to a policy;
2. game replay, which reruns the pinned binary from seeds and actions; and
3. behavioral conformance, which shows adapter actions have the same visible
   effects and turn costs as normal UI actions.

Document each separately and define expected behavior after divergence.
Differential PTY tests (`AUTOMATION_PLAN.md:327-328`) need to compare state,
turn/aut costs, prompts, and RNG progression across a curated action corpus,
not only terminal output. A source adapter that directly invokes internal
functions can otherwise bypass UI confirmations or subtly change game
semantics.

### Low — Several implementation choices are premature or ambiguous

- Supporting JSON and then MessagePack/Protobuf (`AUTOMATION_PLAN.md:119-122`)
  adds migration work without an identified performance problem. Keep one
  versioned encoding until profiling justifies change.
- `native/adapter/` is called optional (`AUTOMATION_PLAN.md:101`) even though a
  native adapter is the central recommendation. Clarify whether the source
  patch, shim, or both implement the protocol.
- “Learned combat statistics” (`AUTOMATION_PLAN.md:214-215`) should distinguish
  public/versioned monster rules from labels derived from hidden after-run
  state. Both may be legitimate offline inputs, but provenance and the live
  observation boundary differ.
- License tracking (`AUTOMATION_PLAN.md:52-54`, `AUTOMATION_PLAN.md:413`) is
  good; Phase 0 should turn it into concrete source-distribution obligations
  for the selected DCSS license and dependencies rather than leave it generic.

## Notable strengths worth preserving

- Exact build/data/config/agent provenance and per-run manifests
  (`AUTOMATION_PLAN.md:18-21`, `AUTOMATION_PLAN.md:275-292`).
- Separate process isolation, run IDs, step IDs, append-only events, resource
  limits, and explicit failure capture (`AUTOMATION_PLAN.md:80-110`,
  `AUTOMATION_PLAN.md:117-122`, `AUTOMATION_PLAN.md:190-200`).
- An explicit player-knowledge belief state rather than direct access to hidden
  world state (`AUTOMATION_PLAN.md:201-207`).
- A layered safety/tactics/navigation/strategy design with learned components
  delayed until the symbolic baseline is trustworthy
  (`AUTOMATION_PLAN.md:209-273`).
- Distributional metrics, uncertainty, ablations, seed separation, property
  tests, scenarios, integration tests, soak tests, and differential tests
  (`AUTOMATION_PLAN.md:294-328`).
- Local-only automation by default and explicit public-server permission and
  licensing concerns (`AUTOMATION_PLAN.md:399-413`).

## Suggested focused edits

1. Recast Phase 0 as a measured interface decision among qw/clua, direct
   WebTiles, PTY, and a minimal source adapter; correct the claim that WebTiles
   requires browser/DOM automation and make qw a baseline or adoption option.
2. Clarify whether the goal is fastest progress toward deep runs or construction
   of a new research platform. If both matter, define separate deliverables and
   benchmark the new player against qw from the first meaningful phase.
3. Narrow the adapter vertical slice and specify its decision hook, dedicated
   transport, prompt lifecycle, action atomicity, ID scoping, error model, and
   normal-UI conformance contract before estimating later phases.
4. Define one complete random-character distribution, including conditional
   weapon/subchoices and RNG separation; archive the full legal manifest from
   the pinned binary and validate support and probability, not merely pair
   counts.
5. Rewrite observation fairness as a player-knowledge projection with paired
   hidden-state noninterference tests. Audit persistent IDs, legal masks,
   action-result fields, remembered cells, manifest access, and offline
   privileged labels explicitly.
6. Replace fixed hidden seeds with frozen paired run manifests plus fresh or
   genuinely sequestered evaluation samples. Specify effect sizes, uncertainty,
   exclusions, retry handling, version boundaries, and useful early-game
   outcomes while win rate is zero.
7. Define progress as an outcome vector—branch entry/end, rune count, Zot/Orb/
   win, XL, score, and depth per branch—and remove or constrain metrics such as
   turns survived that can reward stalling.
8. Prove the console telemetry path in Phase 0, define adapter-emitted milestone
   events if needed, and reconcile every scheduled run even when no final game
   log exists.
9. Complete the runner state machine and retry lineage; use action/turn budgets
   for experimental eligibility and wall time only for fleet safety.
10. Replace action-count exits with mode/transition coverage, rare-state
    scenarios, noninterference checks, forced-failure recovery, conformance
    tests, reconciliation invariants, and a declared invalid-run ceiling.
11. Separate protocol replay, deterministic game replay, and UI-conformance
    testing, with a precise response to divergence for each.
12. Retain one wire encoding and defer simulator/RL/protocol optimization until
    the symbolic baseline and evaluation harness meet their acceptance gates.

## Execution-readiness verdict

**Promising design input, but not ready to implement as the governing plan.**
The reproducibility, fairness, process-safety, artifact, and test disciplines
are excellent foundations. The immediate architecture should remain undecided
until a short spike measures existing clua and direct WebTiles capabilities
against a minimal C++ patch and establishes qw as either the adopted engine or
the baseline. After that, the plan needs a complete randomization contract, a
non-leaking observation projection, credible phase scopes, and an experiment
protocol based on full run manifests. With those changes, it could become a
strong plan for a research-grade DCSS automation platform; without them, it is
likely to spend substantial effort recreating existing interfaces and still
fall short of the stated “as far as possible” objective.
