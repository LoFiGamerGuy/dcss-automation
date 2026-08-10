# DCSS Autonomous Player: Plan and Recommendation

## 1. Objective

Build a reproducible system that can:

1. start a supported version of Dungeon Crawl Stone Soup (DCSS);
2. create a genuinely random, valid character without retrying for a preferred result;
3. observe the game, choose legal actions, and advance without human input;
4. survive interruptions and retain enough evidence to reproduce failures; and
5. improve measurably from “can leave the first room” toward winning the Orb run.

“As far as possible” should be treated as an optimization target, not a promise that
every run wins. The primary score should be win rate over a fixed, hidden set of game
seeds. Secondary scores should reveal progress before wins become common: median XP,
deepest dungeon level, runes collected, turns survived, and milestone completion.

This plan deliberately avoids depending on a particular installed DCSS version. The
first implementation task is to pin a known-good upstream commit and record the game
version, build flags, data files, configuration, character seed, and agent revision in
every run manifest.

## 2. Recommendation in one paragraph

Use a **local, pinned source build of console DCSS** and add a small, versioned
observation/action adapter at the game's source boundary. Run each game in an isolated
worker process. Expose structured state (map cells, visible monsters and items, player
status, inventory, messages, menus, and legal-action context) and accept one semantic
action at a time. Begin with a deterministic rule-based agent that uses DCSS's own
travel/pathing facilities only where their behavior is explicitly understood. Add
record/replay, invariant checks, seed-separated evaluation, and process supervision
before attempting reinforcement learning. Keep a PTY/terminal driver as a black-box
compatibility test and fallback, but do not make OCR, screenshots, or WebTiles the
primary interface.

## 3. Why this architecture

### Source adapter (recommended)

Advantages:

- structured observations avoid lossy screen scraping and terminal-layout ambiguity;
- semantic actions make prompts, inventory letters, targeting, and menus testable;
- deterministic seeds and save handling are easier to control;
- legal-action masks prevent the learning system from wasting most samples on invalid
  keystrokes; and
- the adapter can expose only information already visible to the player, preventing
  accidental “wizard knowledge.”

Costs:

- the adapter must be maintained when upstream internals change;
- distributing a modified DCSS binary/source requires respecting DCSS's applicable
  licenses; and
- it is easy to leak hidden state unless visibility rules are tested explicitly.

### PTY black-box driver (useful fallback, not the main approach)

A console build can be launched under a pseudoterminal and driven with normal keys.
An ANSI terminal emulator can turn output into a stable character/color grid. This is
excellent for end-to-end validation because it exercises the same UI a person uses,
but it is fragile around resize events, animations, prompts, targeting, and versioned
menu text. It should be retained as a smoke-test harness and as a way to prove that
high-level decisions can be translated to an unmodified game.

### WebTiles/browser automation (defer)

Browser automation adds networking, latency, authentication, DOM/canvas extraction,
and server policy concerns without making the decision problem easier. It is a poor
first target. Consider it only after a local agent is competent and only on servers
whose automation rules explicitly permit it.

### Pure machine learning from pixels (do not start here)

DCSS has long horizons, sparse wins, a huge contextual action space, menus, and many
rare interactions. Pixel-only reinforcement learning would spend substantial compute
rediscovering facts the game can safely provide as player-visible structured state.
A hybrid planner can establish a strong baseline and produce demonstrations first.

## 4. Proposed repository shape

Keep the game checkout/build separate from agent code, with the pinned revision in a
lock file rather than committing generated binaries.

```text
.
├── README.md
├── pyproject.toml                 # orchestration/agent package (initially Python)
├── uv.lock or equivalent
├── dcss.lock.json                 # upstream URL, commit, patches, build recipe
├── patches/                       # small reviewable DCSS adapter patches
├── src/dcss_agent/
│   ├── protocol.py                # typed observation/action protocol
│   ├── launcher.py                # process, save-dir, seed, timeout management
│   ├── character.py               # valid-combination discovery and sampling
│   ├── state.py                   # belief state and derived tactical features
│   ├── tactics.py                 # immediate combat/escape decisions
│   ├── strategy.py                # skills, branches, runes, equipment, religion
│   ├── navigation.py              # frontiers, paths, exclusions, retreat routes
│   └── policy.py                  # arbitration and deterministic tie-breaking
├── native/adapter/                # optional compiled protocol shim
├── configs/                       # versioned run/evaluation profiles
├── tests/
│   ├── contract/                  # adapter schemas and visibility guarantees
│   ├── scenarios/                 # tiny saved/replay tactical situations
│   ├── integration/               # real binary smoke tests
│   └── regression/                # seeds that exposed prior defects
├── tools/                         # build, evaluation, report generation
└── runs/                          # gitignored manifests, logs, saves, replays
```

Python is recommended for the first agent because iteration, testing, data analysis,
and ML integration are fast. The DCSS-side adapter should be minimal C++ integrated
with the pinned source. Performance-sensitive inference can move later; turn latency
is unlikely to be the initial bottleneck.

## 5. Observation/action contract

Use a length-prefixed local protocol over stdin/stdout or a Unix-domain socket. JSON is
convenient for the prototype; MessagePack or Protobuf can follow after the schema
stabilizes. Every request and response must include `protocol_version`, `run_id`, and a
monotonically increasing `step_id`.

### Observation

Expose only information available through the normal player interface:

- game version, branch, depth, elapsed auts/turns, and current prompt/mode;
- player position, species/background, XL, HP/MP, attributes, AC/EV/SH, status effects,
  resistances known to the player, piety, transformations, and hunger if applicable to
  the pinned version;
- skills, training targets, spells, abilities, mutations, god data, and known runes;
- inventory/equipment with stable per-observation item IDs and player-visible item
  knowledge (never the hidden true identity of an unidentified item);
- visible/remembered map cells with terrain, features, clouds, items, monsters, staleness,
  and line-of-sight status;
- visible monster properties that the UI normally reveals, plus an agent-maintained ID
  that does not disclose off-screen movement;
- recent messages, interrupt reason, pending prompt/menu, available commands, and the
  result/cost of the previous action; and
- a legal-action mask or explicit context such as `normal`, `targeting`, `inventory`,
  `yes_no`, `more`, `level_up`, and `game_over`.

Do **not** expose the complete generated map, future vaults, unknown item identities,
monster random state, unseen monsters, or combat rolls. Add contract tests proving that
hidden fields cannot affect serialized observations.

### Semantic actions

Start with a compact union type:

```text
Move(direction)                  Wait
Rest(interrupt_policy)           AutoExplore(interrupt_policy)
TravelTo(known_coordinate)       UseStairs(direction)
Melee(direction)                 Fire(target, launcher_or_item)
Cast(spell, target)              Invoke(ability, target)
Use(item_id, mode, target)       Equip(item_id, slot)
Drop(item_id, quantity)          Pickup(item_ids)
SetSkillTraining(changes)        ChoosePrompt(option)
SetExclusion(area)               SaveAndExit
```

The adapter translates semantic actions into the same underlying command paths as the
normal UI where practical. Return a typed error rather than silently consuming a turn.
Record both the semantic action and any generated UI commands for replay/debugging.

## 6. Random character creation

“Random” needs a precise, auditable definition:

1. At startup, obtain the set of species/background pairs accepted by the pinned game.
   Prefer asking the game's character-selection logic rather than duplicating a list.
2. Sample **uniformly over valid pairs** using a dedicated character RNG seeded from
   the run manifest. This differs from independently choosing species and background
   when some combinations are invalid.
3. Use the normal game's random resolution for any background-specific choices, or
   enumerate and uniformly select valid subchoices if the game requires input.
4. Never reroll based on strength, equipment, map, deity availability, or early events.
5. Log the candidate-set hash, RNG algorithm, RNG seed, sampled index, and resolved
   character. Tests should sample many characters and flag statistically implausible
   distributions, while deterministic tests verify identical output for fixed seeds.

Keep character RNG separate from game RNG. Evaluation should include both fully random
characters and per-archetype reporting so a strong result is not merely dominance on
easy combinations.

## 7. Agent design

### Layer 1: process and prompt safety

Before strategy, guarantee that the agent never hangs:

- explicit state machine for every prompt/menu;
- per-step and per-run deadlines;
- heartbeat, memory/CPU limits, graceful save, and forced termination;
- atomic run manifests and append-only event logs;
- detect repeated no-progress observations and trigger a bounded recovery policy; and
- classify terminal states: death, win, saved, crash, protocol error, timeout.

### Layer 2: world and belief state

Maintain a player-knowledge map rather than querying hidden game state. Track explored
frontiers, stairs, shops/altars, exclusions, last-seen threats, item hypotheses, escape
routes, and noise-producing events. Derived features should include reachable safe
tiles, distance-to-stairs, line-of-fire, nearby threat totals, expected incoming damage,
and escape resources. Beliefs must decay or become uncertain when monsters leave view.

### Layer 3: tactical safety controller

Tactics should run on every decision and may veto strategic actions. A conservative
first controller should:

1. estimate each visible monster's threat using player-visible data and learned combat
   statistics;
2. compare fight, reposition, stair retreat, consumable, ability, spell, and escape
   options over a short horizon;
3. preserve multiple escape options and avoid entering unknown adjacent tiles in combat;
4. prefer corridor/door/stair geometry and avoid being surrounded;
5. account for status duration, attack delay, movement speed, ranged attacks, clouds,
   constriction, allies, and noise; and
6. escalate resource use as estimated death probability rises—dying with consumables is
   generally worse than spending them.

Use bounded simulation/expectimax only after combat mechanics are validated. Early
versions should use transparent scoring rules and log a ranked action explanation.

### Layer 4: navigation and exploration

Build paths only through known traversable cells. Attach risk costs for unexplored
frontiers, recent threats, traps, harmful clouds, open rooms, and loss of retreat access.
Autoexplore is acceptable only with strict interrupts; initially, step through paths so
the tactical controller reevaluates every turn. Maintain exclusions around threats and
revisit them when power increases. Clear levels methodically and avoid premature branch
entry based on version-specific strategy tables.

### Layer 5: character development

Classify the random start into capabilities rather than hard-coded “build names”:

- best reliable damage source and its delay/accuracy;
- defenses and HP fragility;
- spell schools, failure rates, and MP economy;
- ranged, summoning, stealth, mobility, and consumable resources; and
- deity opportunities and constraints.

A declarative policy table should choose skill targets, equipment, spells, and religion
from these features. Use milestone-driven training (for example, reliable primary
offense, survivable defenses, key spell failure thresholds) rather than fixed skill
levels. Store rules in versioned data with citations to the game revision or measured
simulations. Do not bake one species/background route into the global policy.

### Layer 6: strategic progression

Represent the campaign as a goal graph, not a fixed script: stabilize the start, locate
key infrastructure, clear safe depth, choose branches based on threats/resistances,
acquire the required runes, enter the endgame, retrieve the Orb, then route to the exit.
Each goal has prerequisites, utility, abort conditions, and fallback goals. The planner
must reassess on new equipment, mutations, deity changes, shafting/teleportation, and
branch discoveries.

### Layer 7: learning (after the baseline is trustworthy)

Use logged runs to improve calibrated threat and action-value models first. Good early
targets are probability of surviving a fight, expected damage over the next few actions,
consumable utility, and retreat timing. Train on semantic observations/actions, split
data by game seed, and evaluate against the unchanged rule baseline. Imitation learning
from strong, legally obtained game logs can initialize a policy, but provenance and
version compatibility must be recorded. Reinforcement learning should use many isolated
local instances and must never see privileged fields absent from production observations.

Keep the hard safety controller around learned policies until controlled ablations show
that removing it improves held-out survival and win rate.

## 8. Reproducibility and artifacts

Each run directory should contain:

```text
manifest.json       # game/agent commits, configs, seeds, platform, build hash
events.jsonl.zst    # observation hash, action, result, timing, policy explanation
game.log            # DCSS messages/milestones
stderr.log          # launcher/adapter diagnostics
save/               # retained on crash or planned checkpoint
terminal.cast       # optional PTY transcript for integration runs
summary.json        # outcome and normalized metrics
```

Avoid storing a full duplicate observation when a delta plus periodic checkpoint is
sufficient. Redact paths/usernames before publishing artifacts. A replay command should
verify observation hashes step by step and report the first divergence. Perfect replay
may depend on upstream RNG behavior, so the pinned binary and data hash are mandatory.

## 9. Evaluation

### Metrics

Report distributions and confidence intervals, not a single best run:

- win rate and Orb retrieval rate;
- rune count, max XL, max depth, branches entered/completed, and score;
- turns/auts survived and real CPU time per decision/run;
- deaths grouped by cause, context, and unused escape resources;
- hangs, crashes, illegal actions, divergence, and save corruption;
- results by species, background, archetype, and game version; and
- ablations against the prior released policy.

### Seed discipline

Maintain development, validation, and hidden evaluation seed sets. Never tune directly
against the hidden set. Rotate/publicize an evaluation set only at release boundaries.
Since a game seed may not capture every source of nondeterminism, also pin character
seed, process environment, locale, terminal size, options, thread settings, and binary
hash. Run enough games to show uncertainty; rare wins require hundreds or thousands of
runs for meaningful comparisons.

### Test pyramid

- **Unit:** protocol validation, random sampling, risk formulas, pathing, prompt machine.
- **Property/fuzz:** malformed observations, menu sequences, arbitrary inventories,
  action serialization, no hidden-data leakage.
- **Scenario:** curated saves/replays for corridors, stairs, ranged threats, status
  effects, targeting, shops, gods, skill changes, and the Orb escape.
- **Integration:** start a fresh pinned binary, create a random character, play a fixed
  number of decisions, save, resume, and replay.
- **Soak:** parallel runs with resource ceilings and automatic crash minimization.
- **Differential:** compare source-adapter actions with equivalent PTY actions on the
  same controlled scenarios.

## 10. Delivery phases and exit criteria

### Phase 0 — version and rules reconnaissance (1–3 days)

- select and pin an upstream stable tag/commit;
- document build/runtime dependencies and applicable licenses;
- identify existing seed, save, scoring, message, input, map, and character APIs;
- decide whether adapter patches can remain small and upstream-rebasable.

**Exit:** a local console game builds reproducibly and a manifest can identify it.

### Phase 1 — launcher and black-box smoke test (2–5 days)

- isolated home/save directories, config, subprocess lifecycle, PTY driver;
- deterministic random-character selection and an action that survives character setup;
- capture terminal transcript, messages, outcome, and artifacts.

**Exit:** 100 consecutive fixed-length starts complete without hang or leaked saves.

### Phase 2 — structured adapter (1–2 weeks)

- observation/action schema, prompt modes, visibility filtering, protocol versioning;
- contract tests and a PTY differential test;
- save/resume and replay hash validation.

**Exit:** the adapter completes 10,000 random legal actions with no crash, information
leak, protocol deadlock, or unclassified prompt.

### Phase 3 — safe baseline player (2–4 weeks)

- world model, exploration, pickup/equipment, basic melee/ranged/spell decisions;
- retreat/rest/resource policies and explainable action ranking;
- generic skill-development rules for every valid random start.

**Exit:** material improvement over a random-action baseline on held-out seeds, with
zero infrastructure hangs and published confidence intervals.

### Phase 4 — campaign competence (ongoing)

- gods, branches, shops, resistances, rune/endgame goal graph, broader prompt coverage;
- systematic death review and minimized regression scenarios;
- dashboards by archetype and milestone.

**Exit:** repeated rune acquisition and occasional held-out wins, not one cherry-picked
seed; every released policy is reproducible from artifacts.

### Phase 5 — learned augmentation (ongoing)

- calibrated threat model, offline imitation/value models, then constrained RL;
- baseline comparisons, ablation studies, model/version registry.

**Exit:** statistically supported held-out improvement with no regression in protocol,
safety, reproducibility, or hidden-information tests.

## 11. Immediate first milestone

The smallest useful vertical slice is a command such as:

```sh
dcss-agent run --game-lock dcss.lock.json --character-seed 101 \
  --game-seed 202 --policy cautious-v0 --max-decisions 1000
```

It should build or locate the pinned console binary, create an isolated run directory,
sample one valid character, start the game, handle all setup prompts, make cautious
movement/rest/retreat decisions for up to 1,000 decisions, and emit a replayable summary.
This proves the interfaces and experiment loop before sophisticated strategy consumes
engineering time.

## 12. Principal risks and mitigations

| Risk | Mitigation |
|---|---|
| Adapter reveals hidden state | Allowlist serialized fields; visibility contract and mutation tests |
| Upstream changes break integration | Pin commits; small patch series; protocol version; scheduled rebase only |
| Agent hangs in a prompt | Explicit prompt state machine, watchdog, transcript, unknown-mode failure |
| Random starts skew results | Uniform valid-pair sampler; audit logs; stratified reporting |
| Evaluation overfits memorable seeds | separated hidden seeds, aggregate statistics, release-only evaluation |
| Saves/logs become incompatible | record binary/data hash; treat cross-version resume as unsupported by default |
| Rules become unmaintainable | capability-based modules, declarative versioned tables, scenario tests |
| Learned policy exploits instrumentation | same observation allowlist in training and production; PTY differential tests |
| Parallel games corrupt shared state | per-run directories, immutable game data, no shared save or rc files |
| Automation violates a public server policy | run locally by default; obtain explicit permission before remote play |
| Licensing is overlooked | inventory upstream and dependency licenses before distribution |

## 13. Decisions to defer until Phase 0 evidence exists

- exact upstream tag/commit and whether to track stable releases or trunk;
- precise build flags and seed controls supported by that revision;
- JSON versus a binary wire encoding;
- whether the adapter is a patch, compile-time mode, or in-process library boundary;
- use of the game's built-in travel/autoexplore versus agent-owned equivalents;
- combat simulator fidelity and the first ML framework; and
- public-server/WebTiles support.

Deferring these prevents early architecture from relying on remembered behavior from a
different DCSS release. Phase 0 should resolve each item with a short decision record and
a test against the pinned source.

## 14. Reference starting points

Validate these against the revision selected in Phase 0 rather than treating them as
timeless API documentation:

- DCSS upstream source and build documentation: <https://github.com/crawl/crawl>
- Official project site and release information: <https://crawl.develz.org/>
- In-game documentation in the pinned source tree, especially command, options, species,
  background, skill, spell, religion, and branch references
- The pinned source's character-selection, input, map-knowledge, save, scoring, and test
  code, which should be considered authoritative for the adapter

## 15. Definition of success

The project succeeds incrementally when it is a dependable experimental platform, not
only when it wins. A credible first release starts any valid random character, plays
without intervention, never uses unseen information, explains and replays its decisions,
and produces statistically comparable results. From that foundation, every death can
become a regression case, every policy change can be measured, and rare deep runs can be
converted into repeatable progress toward an autonomous win.

