# Plan: A fully-random-character DCSS bot that gets as far as possible

**Goal.** Build a system that (1) launches Dungeon Crawl Stone Soup, (2) rolls a
*completely random* character (any legal species × background × weapon), and
(3) plays that character autonomously as deep into the game as it can get,
over and over, with measurable progress.

This document is a reviewed-before-building plan: what exists today, the
implementation options, a concrete recommendation, and a phased roadmap.

---

## 1. Success criteria

"As far as possible" needs a metric, because wins will be rare with random
characters (many random combos are objectively bad, and even the best bot ever
written has a low win rate). Proposed primary metrics, in order:

1. **Milestone ladder** per game: D:1 → Temple → Lair → Orc → first Lair
   branch → first rune → Vaults → Depths → second/third rune → Zot → Orb →
   win. Zot entry requires 3 runes, so runes are the natural "distance" unit.
2. **Score** (crawl's own score formula: XP-weighted, +10k per rune plus a
   quadratic rune bonus, +250k for a win) — comparable across combos.
3. **XL and max dungeon depth reached** as tiebreakers.

Aggregate metrics across many games: median/best milestone, milestone
histogram per species and background, win count. A run archive (morgues +
logfile + milestones) is the ground truth; crawl writes all of these natively.

Explicit non-goal for v1: winning consistently. The first bot to ever win DCSS
unassisted (`qw`) peaked around ~15% wins with its *single best* combo and ~1%
for 15-rune games; a uniformly random combo pool will be far below that. The
interesting output is the progress distribution and pushing it upward.

---

## 2. What already exists (research summary)

Three research passes were done against the crawl source tree, the qw source,
and the broader ecosystem. Key facts the plan relies on:

### 2.1 Ways to control crawl programmatically

| Interface | What it is | Pros | Cons |
|---|---|---|---|
| **clua (rc-file Lua)** | Lua embedded in the game; `ready()` hook fires before every input prompt; full read API (`you`, `monster`, `view`, `items` modules) + key/command injection (`crawl.sendkeys`, `crawl.do_commands`) | Structured state, no parsing, runs in-process at full speed, proven (qw) | Logic must be Lua inside the game process; public servers throttle Lua CPU/memory |
| **WebTiles WebSocket (JSON)** | The web client protocol: zlib-compressed JSON messages (`player`, `map`, `msgs`, `input_mode` in; `key`/`input` out) against a local or public webtiles server | Language-agnostic external process; full symbolic state; existing client libs (`dcss-api` Rust/Python, supports 0.29–0.34; dcss-ai-wrapper; nkhoit/dcss-ai's pure-Python client) | Must run/manage a server (trivial locally: Tornado + `WEBTILES=y` build); protocol plumbing (compression, batching, menus/prompts) |
| **pty screen-scraping** | Drive console crawl via pexpect/tmux and parse the ANSI screen | Works anywhere | No structured state; fragile; strictly worse than the above — rejected |

There is **no official "crawl API"**; clua and webtiles are the two sanctioned
surfaces. A useful hybrid exists: helper clua in the rc file that pre-digests
state or auto-answers prompts, while an external process drives keys.

### 2.2 Character randomization is built in

Crawl natively supports fully random characters with zero menu interaction:

- rc options: `name = <s>` (bypasses the main menu) + `fully_random = true`
  (any legal combo), or `species = viable` / `background = viable`
  (recommended-only randomness), or explicit `combo = MiBe.handaxe` /
  multi-value lists (random pick among entries), `weapon = random|viable`.
- CLI: `-name`, `-species`, `-background`, `-rc`, `-seed <n>`, `-wizard`,
  `-headless`, `-lua-max-memory <MB>`, `-no-throttle`, and
  `-extra-opt-last "opt=val"` to inject any rc option.
- `crawl -list-combos` enumerates every legal combo (qw's
  `util/hypercombogen.sh` already turns this into a combo list with sensible
  starting weapons) — this gives us *controlled* full randomness: our harness
  can sample uniformly and log exactly what was rolled.

Current game (0.34/trunk): **27 species × 26 backgrounds ≈ ~700 legal
combos**, including pathological ones a bot must survive: Mummy (no potions),
Felid (no weapons/armour), Gnoll (no selective skill training), Djinn (HP=MP
pool), Demigod (no gods), Poltergeist (no body armour), Coglin (no jewellery),
Formicid (no teleport/berserk/haste), Octopode (no armour, 8 rings).
Impossible combos (e.g. Felid Gladiator) are excluded from the legal list by
the game itself.

### 2.3 Prior art

- **qw** (github.com/crawl/qw, maintained by the DCSS devteam; ~19k lines of
  Lua across 43 modules) is the state of the art and the only bot with
  unassisted wins, including 15-rune wins and the first-ever Djinni/Demigod
  wins (0.31 tournament, 2024). It runs entirely as rc-file clua: a `ready()`
  hook drives a coroutine main loop; a prioritized **plan cascade**
  (emergency → attack → rest → explore) picks one action per turn; subsystems
  cover threat-scored retreat/flee/stairdancing, equipment-set optimization,
  skill-training utility functions, 13 partially-supported gods, a `GOALS`
  route language ("Normal" ≈ optimal 3-rune route), Abyss/Pan/Zig/Tomb/Hell
  special cases, and cross-game persistence (`c_persist`) with a
  **`COMBO_CYCLE_LIST`** mechanism for cycling combos between games.
  Weaknesses: essentially no spellcasting (casters are played as bad melee),
  many god/species abilities unused, low win rate outside its favored
  melee combos (best: GrFi/GrBe/MiFi/MiBe/GrHu/MiHu with Okawaru/Trog/Ru).
  Version coupling: one qw release per crawl version (0.1.0→0.29 …
  master→0.32-a0); no runtime version abstraction.
- **dcss-api** (EricFecteau): maintained Rust+Python webtiles client,
  DCSS 0.29–0.34, plus a YAML scenario builder for reproducible tests.
- **dcss-ai-wrapper** (dtdannen): research-oriented webtiles API (PDDL/RL
  state), the main academic use of DCSS; low activity since ~2022.
- **nkhoit/dcss-ai** (2025–26): LLM agent (fresh session per life, 39 discrete
  tools, `learnings.md` carried across deaths) on a local Dockerized webtiles
  server. No documented deep runs yet.
- **LLM-agent reality check**: on BALROG, frontier LLMs still score
  single-digit progression on NetHack (a comparable roguelike); the NetHack
  Challenge was won decisively by a *symbolic* bot (AutoAscend). Pokémon runs
  needed 100k+ actions and weeks even with heavy harnesses. Conclusion: an
  LLM cannot be the *inner loop* of a DCSS bot today — a full game is tens of
  thousands of turns and permadeath punishes every hallucination — but an LLM
  can plausibly help as a low-frequency strategic layer or as an offline
  policy-improvement tool.

---

## 3. Options considered

**A. Adopt qw + build a randomization/metrics harness around it.**
Proven engine; "random character" and "run forever, measure progress" become
harness features (combo sampling, batch running, stats). Fastest route to deep
runs; we inherit qw's weaknesses (no casting) but can patch them incrementally
upstream-style in Lua.

**B. Write a fresh external bot on webtiles (Python, via dcss-api or a small
custom client).** Full ownership, nicer language/tooling, LLM-integration
friendly, testable with seeded scenarios. But we'd be re-deriving years of
tactical edge-case handling (stairdancing, threat scoring, Abyss recovery,
prompt handling); realistically months to reach "sometimes gets a rune".

**C. Pure LLM agent.** Highest novelty, worst floor: cost/latency per
decision, and the evidence says it plateaus far above the dungeon floor but
far below the Orb. Better as an add-on than a foundation.

**D. RL.** Out of scope: no existing DCSS gym at the full-game level,
enormous sample cost, and the action/observation engineering alone dwarfs
options A+B.

**Recommendation: A as the backbone, B's harness as the shell, C as an
optional experimental layer.** Concretely: a Python **harness** owns game
lifecycle, character randomization, logging and stats; **qw (pinned +
patched)** is the player. This is also the least-regret path: the harness
(Phase 1) is identical no matter which player engine sits inside it, so if we
later want to grow our own webtiles bot or an LLM layer, the
launcher/metrics/archive infrastructure carries over unchanged.

---

## 4. Recommended architecture

```
┌────────────────────────── harness (Python) ──────────────────────────┐
│ runner.py      – spawn crawl per game, timeouts, crash recovery      │
│ combos.py      – sample uniformly from `crawl -list-combos` output;  │
│                  emit per-game rc fragment (combo, god/goal hints)   │
│ collect.py     – parse logfile/milestones/morgues into SQLite        │
│ report.py      – progress histograms, per-species/background tables, │
│                  best-run leaderboard (markdown/HTML report)         │
└──────────────┬───────────────────────────────────────────────────────┘
               │  crawl -rc generated.rc -name bot### -seed ... 
┌──────────────▼───────────────────────────────────────────────────────┐
│ crawl (pinned source build, console/headless, -lua-max-memory 128    │
│        -no-throttle)                                                 │
│   └── qw.lua (pinned qw + our patches) — ready() hook plays the game │
└──────────────────────────────────────────────────────────────────────┘
```

Key design decisions:

1. **Local pinned build, not public servers.** qw is explicitly not allowed on
   official servers (Lua CPU/memory limits), and local play is orders of
   magnitude faster (qw finishes games in minutes of wall-clock). Pin crawl to
   the version qw master targets (0.32-a0 at last check; verify against qw's
   changelog at build time) via a submodule or documented commit hash.
   Build: `make` in `crawl-ref/source` (console build; no tiles needed).
2. **Randomization lives in the harness, not in `fully_random = true`.**
   Generating the combo per game ourselves (from `-list-combos`) gives us:
   uniform-vs-weighted sampling as a config choice, exact logging of the roll,
   reproducible re-runs (combo + `-seed`), and the ability to attach per-combo
   god/goal configuration (qw's `COMBO_CYCLE_LIST` syntax `SpBg.weapon^gods`
   already supports this). `fully_random = true` remains a documented
   fallback and a purity check that our sampler matches the game's own
   legal-combo set.
3. **God choice policy for random characters:** zealot backgrounds keep their
   start god; otherwise default `GOD_LIST = Okawaru/Trog/Makhleb` (qw's
   strongest), with a per-species override table we grow over time (e.g.
   Demigod → no god; casters → whatever we teach qw to use). This table is
   one of the main tuning surfaces.
4. **One game = one process invocation**, wizard mode off, `AUTO_START` on,
   `QUIT_TURNS` safety net on (qw quits after 1000 stuck turns) plus a
   harness-level wall-clock timeout with save-backup, so a single hung game
   never stalls the fleet. Batch parallelism via N independent crawl dirs
   (qw's `util/batch-qw.sh` shows the pattern; we'll own our version).
5. **Everything is a run artifact.** Per game: sampled combo, seed, qw
   version, crawl version, final milestone, score, turn count, death reason,
   morgue path — one SQLite row. Reports are regenerated from the DB.

### Repository layout (proposed)

```
dcss-automation/
├── PLAN.md                  (this file)
├── harness/                 Python package: runner, combos, collect, report
├── player/qw/               qw checkout (submodule) + patches/ overlay
├── vendor/crawl/            crawl checkout (submodule, pinned)
├── config/                  rc templates, god-policy table, sampler weights
├── scripts/                 build-crawl.sh, run-batch.sh, make-report.sh
└── runs/                    (gitignored) morgues, logfiles, results.sqlite
```

---

## 5. Roadmap

### Phase 0 — Foundation (short)
- Vendor + build pinned crawl; vendor qw at the matching tag; `make-qw.sh`.
- Smoke test: one manual qw game with the stock `GrBe.handaxe` runs to
  completion (death or win) headlessly.
- **Exit criterion:** `scripts/run-one.sh` plays a full unattended game and a
  morgue file appears.

### Phase 1 — Random-character fleet (the core deliverable)
- Combo sampler from `-list-combos` (+ starting-weapon assignment à la
  hypercombogen); per-game rc generation; god policy table v0.
- Batch runner with timeouts, crash/save recovery, parallel instances.
- SQLite collector + report generator (progress ladder, per-species and
  per-background tables, score distribution).
- **Exit criterion:** a 500–1,000 game random-combo campaign completes
  unattended and produces a report. This *is* the user-visible goal: start
  DCSS, random character, go as far as possible — measured.

### Phase 2 — Raise the floor (iterative, data-driven)
Use Phase 1's report to attack the worst buckets. Expected early findings and
matching work items, in likely priority order:
- **Caster backgrounds** (~40% of the combo pool): teach qw minimal
  spellcasting — cast the starting attack spell when it beats melee, train
  the school, learn the level-2/3 book follow-ups. Even "Magic Dart until
  Lair" massively beats qw's current played-as-melee behavior.
- **Special species handling:** Felid (no-weapon combat plans), Mummy (never
  plan around potions), Gnoll (skip training logic), Djinn (HP-cost casting),
  Formicid (no-teleport escapes), Demigod (no-god goals).
- **God coverage:** extend the per-species/background god policy; consider
  adding basic support for currently-unused strong gods where it moves the
  needle.
- Each change ships behind a config flag and is validated by an A/B campaign
  (same seeds, sampler, and game version) — the harness makes this cheap.
- **Exit criterion (target):** median random-combo game reaches Lair; ≥10% of
  games reach a rune; first random-combo wins observed.

### Phase 3 — Experimental layers (optional, parallel)
- **LLM strategic advisor:** at low-frequency decision points (god choice,
  branch order, "should I dive or grind", shopping) export qw's state and let
  an LLM adjust the `GOALS`/config knobs between levels or between games —
  the inner loop stays symbolic. Cross-game: an LLM post-mortem over morgues
  proposing god-policy/sampler/config patches ("policy improvement by PR").
- **Webtiles spectating:** run a local `WEBTILES=y` server so humans can watch
  the bot live; also enables the dcss-api scenario builder for regression
  tests of tactical situations.
- **Own-bot track (long shot):** if we outgrow Lua, port the plan-cascade
  architecture to Python over webtiles, using qw as the reference
  implementation and the Phase 1 harness unchanged.

---

## 6. Risks and open questions

| Risk | Mitigation |
|---|---|
| qw master lags crawl trunk (last public commit mid-2024; targets 0.32-a0) | Pin crawl to qw's supported version — we control the whole stack locally, so being one version behind costs nothing. Revisit per qw release. |
| Random combos crash qw's assumptions (untested species/background paths) | qw's stuck-plans + `QUIT_TURNS` + harness timeout bound the damage; failures land in the report as their own bucket and become Phase 2 work items. |
| clua Lua memory/CPU limits | `-lua-max-memory 128 -no-throttle` locally (qw's documented requirements). |
| Long-tail hangs / infinite loops across ~700 combos × many games | Per-game wall-clock kill + save backup + resume-or-abandon logic in the runner. |
| Score/milestone parsing drifts across versions | Parse crawl's own logfile/milestones (stable, machine-readable) rather than morgue text. |

Open questions for review (defaults chosen, but flagging):
1. **Uniform over all legal combos, or over species (then background)?**
   Default: uniform over combos. (Uniform-over-species doubles the weight of
   restricted species like Felid/Demigod that ban many backgrounds.)
2. **Should weapon choice be random too, or "best for combo"?** Default:
   sensible starting weapon per combo (hypercombogen style); pure-random
   weapon is a config flag.
3. **Wizard-mode metrics runs?** qw supports `WIZMODE_DEATH` for faster
   iteration, but scores/milestones are only "real" in normal mode. Default:
   normal mode for campaigns, wizard mode allowed for debugging.
4. **Is the LLM layer (Phase 3) in scope at all, or symbolic-only?**

---

## 7. Appendix: primary sources

- crawl source: github.com/crawl/crawl — `l-you.cc`, `l-moninf.cc`,
  `l-view.cc`, `l-item.cc`, `l-crawl.cc` (clua API); `newgame.cc` (random
  chargen keys `*`/`+`/`!`/`#`); `docs/options_guide.txt` (`fully_random`,
  `combo`, `species/background/weapon = viable`); `main.cc` (CLI flags,
  `-headless`, `-seed`, `-lua-max-memory`, `-no-throttle`, `-list-combos`);
  `hiscores.cc` (score formula); `webserver/` + `tileweb.cc` (webtiles
  protocol).
- qw: github.com/crawl/qw (43-module source, `qw.rc`, `make-qw.sh`,
  `util/hypercombogen.sh`, `util/batch-qw.sh`, `docs/accomplishments.md`,
  changelog with per-crawl-version tags); historical repo github.com/elliptic/qw.
- Ecosystem: github.com/EricFecteau/dcss-api (webtiles client, 0.29–0.34),
  github.com/dtdannen/dcss-ai-wrapper (+ arXiv 1902.01769 "DCSS as an
  Evaluation Domain for AI"), github.com/nkhoit/dcss-ai (LLM agent),
  github.com/alotofdavid/beem.
- LLM-agent evidence: BALROG benchmark (arXiv 2411.13543), NetPlay (arXiv
  2403.00690), NetHack Challenge/AutoAscend, Claude/Gemini Pokémon runs.

*Facts above were gathered from the crawl and qw source trees and public docs
in August 2026; items that could not be fully verified (exact current qw↔crawl
trunk compatibility, some historical win statistics) are treated as
assumptions to re-check during Phase 0.*
