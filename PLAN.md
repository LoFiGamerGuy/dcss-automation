# Plan: A fully-random-character DCSS bot that gets as far as possible

**Revision 2.** This version incorporates the author self-review
(`review/SELF_REVIEW.md`) and the independent review + synthesis
(`review/INDEPENDENT_REVIEW.md`, `review/REVIEW_SYNTHESIS.md`), applying the
synthesis's consolidated 12-item edit list. Major changes from v1: an explicit
randomness contract; a resolved version-targeting decision; a source-backed
telemetry design (local console builds do **not** write the `milestones` file
by default); an outcome-vector metric replacing the linear milestone ladder;
a real experiment protocol; a runner state machine with run accounting; an
enforceable fairness contract; and acceptance-test phase exits.

**Goal.** Build a system that (1) launches Dungeon Crawl Stone Soup, (2) rolls
a random character under a precisely defined distribution (see §2), and
(3) plays that character autonomously as deep into the game as it can get,
over and over, with measurable progress.

---

## 1. Success criteria

"As far as possible" needs a metric, and wins will be rare: random characters
include many objectively weak combos, and even the best existing bot has a low
win rate with hand-picked ones. v1's single "milestone ladder" was a route,
not a measurement — Temple is optional, Orc/Lair order varies, branch choice
varies — so progress is recorded as an **outcome vector of independent
monotone indicators** per game:

- branch entered / branch end reached, per branch (Temple, Lair, Orc, each
  Lair sub-branch, Vaults, Depths, Zot, plus extended branches);
- rune count; Orb picked up; game won;
- XL reached, score, turns/auts survived, deepest level *per branch*
  (cross-branch depth is not comparable and is never summed);
- terminal status (death/quit/timeout/crash — see §6 state machine) and
  death cause where applicable.

Reports keep the full vector, stratified by species, background, and
archetype. When a scalar is needed for tuning, the declared optimization
objective is **lexicographic: (runes, Zot entered, Depths entered, Vaults
entered, first-Lair-branch entered, Lair entered, XL), ties broken by
score** — chosen because rune count is the game's own difficulty gate (Zot
requires 3 runes). Changing this objective is a versioned decision, not a
reporting tweak.

Explicit non-goal for v1: winning consistently. Historical context (treat as
dated evidence, not a benchmark: elliptic-era qw README and arXiv 1902.01769):
qw's best offline 3-rune winrate was reported ~15% with Deep Dwarf Fighter — a
species since removed — and ~1% for 15-rune games with its best combo. A
random pool will be far below that. The deliverable is the progress
distribution and the machinery to push it upward.

---

## 2. Randomness contract

"Completely random" is defined here precisely, because crawl's own
`fully_random` option is **not** uniform: per 0.32-era `newgame.cc`, native
fully-random chargen randomly picks whether to resolve species or background
first, samples that dimension, then samples a compatible value in the other —
which weights pairs unevenly. We define our own distribution instead of
emulating crawl's:

**Default treatment — `uniform-pairs`:**
1. Enumerate the legal (species, background) pairs **from the pinned crawl
   executable** (via `-list-combos`, an undocumented-but-real flag that emits
   pairs only; pin-tested in Phase 0). Hash and archive this manifest.
2. Sample one pair uniformly, using a dedicated character-RNG seeded from the
   run manifest — separate from the game seed.
3. If the background offers a starting-weapon choice, sample **uniformly over
   that background's legal weapon options** for the chosen species (option set
   enumerated from the pinned executable at Phase 0, since `-list-combos`
   does not cover weapons). Backgrounds without a weapon choice have no
   weapon dimension.
4. Never reroll for any reason (stats, equipment, god availability, map).
5. Log: manifest hash, RNG seed, sampled indices, resolved character.

**Named alternative treatments** (config-selected, never the default, always
labeled in reports): `curated-weapons` (hypercombogen-style "sensible" weapon
per combo — useful for comparability with qw's historical results, but it is
curation, not randomness); `crawl-native` (`fully_random = true`, crawl's own
distribution, kept as a behavioral cross-check).

**Validation (Phase 0/1 acceptance tests):** the sampler's support set must
exactly equal the executable's legal set (diff test); a large-sample
goodness-of-fit test must match the declared uniform probabilities; fixed
seeds must reproduce identical characters.

---

## 3. Version targeting decision

qw is version-coupled (one release per crawl version; public master's
changelog targets DCSS 0.32-a0, last commit July 2024). v1 was internally
inconsistent about this; resolved as follows:

- **The product targets the qw-compatible pair, not current DCSS.** Phase 0
  selects and pins **exact immutable commits** of both crawl and qw that are
  demonstrated compatible (starting from qw master + a crawl commit near the
  0.32-a0 changelog reference, adjusting empirically). Every run manifest
  records both hashes plus patch/config/schema hashes.
- All species/background statements in this plan are therefore about the
  pinned version, and the legal-character manifest is generated from the
  pinned binary — not from trunk documentation. (Trunk-era facts from v1,
  e.g. Poltergeist, may simply not exist in the pinned pool.)
- Compatibility is proven by **canaries**, not one smoke test: a Phase 0
  suite covering a weapon-choice background, a zealot (god-locked)
  background, a caster, and restrictive species (at minimum Felid, Mummy,
  Gnoll, Demigod, Formicid, plus the default GrBe) each running N decisions
  without protocol error.
- Revisiting the pin (e.g. when qw supports a newer crawl) is a versioned
  decision with a fresh manifest and canary pass. The cost of being behind
  trunk is accepted and documented, not denied.

---

## 4. What already exists (research summary)

Verified-vs-unverified status for every claim here is tracked in
`review/REVIEW_PACKET.md` §3; unverified numbers are labeled hypotheses.

### 4.1 Ways to control crawl programmatically

| Interface | What it is | Pros | Cons |
|---|---|---|---|
| **clua (rc-file Lua)** | Lua embedded in the game; `ready()` hook fires before every input prompt; player-knowledge-limited read API (`you`, `monster`, `view`, `items`) + key/command injection | Structured state, no parsing, in-process speed, proven (qw) | Logic must be Lua inside the game process; servers throttle it |
| **WebTiles WebSocket (JSON)** | The web client protocol: structured `player`/`map`/`msgs`/`input_mode` messages from the crawl binary itself | Language-agnostic external process; existing clients (`dcss-api`, 0.29–0.34) | Server/protocol plumbing; not needed for the core deliverable |
| **pty screen-scraping** | Parse the ANSI screen | Works anywhere | Lossy, fragile — rejected |

There is no official "crawl API"; clua and webtiles are the sanctioned
surfaces. The clua read API is player-knowledge-limited by construction
(monster damage in bands, unseen monsters return nil, item info
identification-gated — verified in `l-moninf.cc`/`l-item.cc`), which is the
basis of the fairness contract in §7.

### 4.2 Prior art

- **qw** (github.com/crawl/qw, devteam-maintained; ~19k lines of Lua, 43
  modules): the only bot with unassisted DCSS wins. rc-file clua; `ready()`
  drives a coroutine main loop; prioritized plan cascade (emergency → attack
  → rest → explore); threat-scored retreat/flee/stairdancing; equipment-set
  optimization; skill-training utility functions; 13 partially-supported
  gods; `GOALS` route language; Abyss/Pan/Zig/Tomb special cases; cross-game
  persistence (`c_persist`); `COMBO_CYCLE_LIST` for per-game combos.
  Weaknesses: essentially no spellcasting (casters played as weak melee),
  many abilities unused, low win rate outside favored melee combos.
- **dcss-api** (EricFecteau): maintained Rust+Python webtiles client with a
  scenario builder — relevant only to the deferred webtiles track.
- **dcss-ai-wrapper** (dtdannen) and **nkhoit/dcss-ai** (LLM agent): prior
  research interfaces; no deep autonomous runs documented.
- **LLM-agent evidence** (secondary sources, labeled hypothesis-grade):
  frontier LLMs score single-digit progression on NetHack (BALROG); the
  NetHack Challenge was won by a symbolic bot. Conclusion stands: an LLM
  cannot be the inner loop; it may serve as a low-frequency advisor (§9).

### 4.3 Options considered (unchanged from v1)

**A.** qw + randomization/metrics harness — fastest to deep runs; inherit
qw's weaknesses, patch incrementally. **B.** Fresh webtiles bot — full
ownership, months to re-derive tactical knowledge. **C.** Pure LLM agent —
plateaus far below the Orb; add-on, not foundation. **D.** RL — out of
scope. **Recommendation: A**, with the harness designed so the player engine
sits behind a narrow adapter interface (§5) — reuse of the harness for B/C is
plausible but *not* claimed to be free: lifecycle, transport, and prompt
handling would change; only the artifact schema and reporting carry over
as-is.

---

## 5. Recommended architecture

```
┌────────────────────────── harness (Python) ──────────────────────────┐
│ runner.py      – run state machine, per-run dirs, timeouts, recovery │
│ combos.py      – randomness contract (§2): manifest, sampler, tests  │
│ collect.py     – telemetry (§6) → SQLite; write-ahead run accounting │
│ report.py      – outcome-vector reports, stratified tables, CIs      │
│ adapter.py     – narrow player-adapter interface (launch cmd, rc     │
│                  fragment, end-of-run artifact spec) — qw impl only  │
└──────────────┬───────────────────────────────────────────────────────┘
               │  crawl -rc generated.rc -name <run_id> -seed ...
┌──────────────▼───────────────────────────────────────────────────────┐
│ crawl (pinned commit, console build + telemetry define (§6),         │
│        -lua-max-memory 128 -no-throttle)                             │
│   └── qw.lua (pinned commit + patches) — ready() hook plays the game │
└──────────────────────────────────────────────────────────────────────┘
```

Key decisions:

1. **Local pinned builds only** (§3). qw is not allowed on public servers
   (Lua CPU/memory limits). "Local play takes minutes per game" is a
   hypothesis — Phase 0 measures median/p95 wall-clock, CPU, and memory per
   game *before* fleet sizing, timeouts, or campaign budgets are chosen.
2. **Randomization lives in the harness** per the §2 contract; crawl-native
   `fully_random` is retained only as a named alternative treatment.
3. **God choice policy:** zealots keep their start god; otherwise default
   `GOD_LIST = Okawaru/Trog/Makhleb` (qw's strongest), with a per-species
   override table (Demigod → none, etc.). The god policy is *play* policy,
   not part of the randomness contract, and is versioned config.
4. **Vendoring:** exact-commit checkouts of crawl and qw. Mechanism
   (submodule vs. pinned shallow clone) and qw patch mechanism (overlay vs.
   fork) are Phase 0 decisions recorded in a short decision note — they are
   workflow preferences, not correctness issues.
5. **Everything is a run artifact** (§6): write-ahead manifest before launch,
   append-only event capture, one reconciled SQLite row per scheduled run.

---

## 6. Telemetry, runner state machine, and run accounting

### Telemetry (corrected from v1)

v1 assumed local crawl writes a `milestones` file natively. **It does not:**
`mark_milestone` writes the milestones xlog only under the `DGL_MILESTONES`
define, which stock `AppHdr.h` enables inside the `DGAMELAUNCH` (server)
block — a plain local console build produces no milestones file (verified
against 0.32-era source by the independent review).

Design, in preference order, resolved in Phase 0:
1. **Build with `DGL_MILESTONES` enabled** (small build-flag/patch; Phase 0
   verifies the file appears and asserts exact expected event records and
   fields for a scripted game — branch entry, rune, death).
2. **Fallback — reduced metric set** from artifacts a stock build does
   produce: the final logfile row (`place`, `urune`, `xl`, `sc`, `tmsg`, …)
   plus the morgue's turn-stamped notes. If the fallback is used, the report
   drops any indicator the final xlog cannot prove and says so — no silent
   degradation.

The Phase 0 exit asserts *correct parsed events*, not "a morgue appeared".

### Runner state machine

Every run terminates in exactly one status:
`won | died | quit_intentional | quit_stuck (qw QUIT_TURNS) | lua_error |
crashed | timeout_turns | timeout_wall | invalid_telemetry | harness_failure`.

- **Budgets are in-game:** the per-run cap is a *turn/action* budget
  (`timeout_turns`), because a wall-clock cap makes policy speed and host
  load affect game outcomes — an evaluation confound. Wall-clock
  (`timeout_wall`) exists only as a generous operational circuit breaker and
  those runs are excluded from gameplay metrics (counted and reported as
  infrastructure failures).
- **Hang detection is progress-based** (no save/logfile/message mtime change
  for N minutes), not just elapsed time; on trigger, capture crawl's message
  log and stderr, attempt one graceful save, then kill.
- **No resume into metrics:** "one game = one process invocation" is kept
  strict for measured runs — a run that dies mid-flight is terminal with its
  status; resume-from-save exists only as a debugging tool and resumed games
  never enter campaign metrics (this resolves v1's save-backup/resume
  contradiction).
- **Per-run isolation:** unique run ID, own crawl dir, own name; no shared
  save/rc/logfile state between parallel workers.

### Run accounting

A **write-ahead manifest** row (run ID, character, seeds, all version/config
hashes) is committed *before* launch; the collector reconciles scheduled vs.
terminal runs so a crash that produces no final logfile row is still
attributed, never silently dropped, and retries (infrastructure failures
only) carry lineage and are never double-counted. A report invariant checks:
every scheduled run appears exactly once with a terminal status.

---

## 7. Fairness contract (observation boundary)

The bot must act only on player-knowable information. Current status: the
qw/clua path is fair **by construction** (§4.1), verified against the clua
source. To keep it true as the system grows, the contract is explicit:

- A live policy may receive only state exposed through the
  player-knowledge-limited clua surface (or a future adapter audited to the
  same standard).
- The following never reach a live policy: the game seed, raw save data,
  source/full-map internals, final telemetry of the current run, and any
  knowledge from a *prior attempt at the same evaluation seed*.
- `c_persist` (qw's cross-game memory) is cleared between games in any
  campaign that reuses seeds; campaigns with fresh random seeds may keep it.
- Wizard-mode runs never enter evaluation metrics (rule, not default).
- Telemetry files are read-only to the game process during a run.
- Each future adapter (webtiles, LLM advisor) requires a fresh fairness
  audit before its runs count.

Phase 1 includes probe tests: assert that unseen monsters and unidentified
item identities are absent from everything the policy layer can read.

---

## 8. Experiment protocol

Applies to every claimed improvement (Phase 2 onward):

- **Frozen manifests:** an experiment fixes a manifest of (character, seed)
  pairs generated under the §2 contract; both policy arms run every entry
  from clean state (cleared `c_persist`, fresh dirs).
- **Splits:** development seeds (used freely), validation seeds (compared
  against, sparingly), and an untouched holdout set evaluated only at
  release points. Identifying weak buckets and validating their fixes on the
  same campaign data is overfitting; bucket-targeted fixes are confirmed on
  fresh seeds.
- **Seed semantics, stated precisely:** a seed fixes the initial PRNG state
  (dungeon and gameplay); once policies act differently they consume the
  stream differently and trajectories diverge. Same-seed arms are variance
  control, not paired observations — analysis treats runs as independent
  samples per arm.
- **Pre-declared analysis:** primary outcome(s) named in advance (default:
  rune-rate and Lair-entry rate), effect sizes with confidence intervals,
  a minimum practically-meaningful effect, and a sample size sized for it
  (at low base rates this is hundreds-to-thousands of games per arm — the
  Phase 0 throughput measurement feeds this budget). Non-game-ending
  outcomes (`timeout_wall`, `crashed`, …) are counted per the §6 status
  taxonomy and reported, never silently excluded. Multiple comparisons
  across many buckets are acknowledged and corrected for, or demoted to
  exploratory.
- **Provenance:** every run records crawl/qw/patch/config/sampler/schema
  hashes; an experiment is reproducible from its manifest alone.

---

## 9. Roadmap

### Phase 0 — Foundation and reconnaissance
Work: pin exact crawl+qw commits (§3); build with the telemetry define (§6);
generate and archive the legal-character manifest and weapon-option sets
(§2); measure per-game wall-clock/CPU/memory over ~50 mixed games; write the
vendoring/patch-mechanism decision note; verify `-list-combos` behavior on
the pinned binary.
**Exit (acceptance tests, not existence checks):**
- reproducible build from the lock info on a clean machine;
- telemetry test asserts exact expected milestone/logfile records for a
  scripted short game;
- canary suite (§3: GrBe + weapon-choice, zealot, caster, Felid, Mummy,
  Gnoll, Demigod, Formicid) each completes N decisions without protocol
  error, hang, or unclassified prompt;
- sampler support-set diff vs. the executable's legal set is empty;
- throughput report exists and feeds Phase 1 sizing.

### Phase 1 — Random-character fleet (core deliverable)
Work: sampler + per-game rc generation; god policy v0; runner state machine,
write-ahead accounting, progress-based hang detection (§6); collector +
outcome-vector report (§1) with stratified tables.
**Exit (acceptance tests):**
- sampler goodness-of-fit test passes at campaign scale;
- forced-failure drills (induced Lua error, kill -9, hang) each land in the
  correct terminal status with artifacts attributed;
- parallel-isolation test: N workers, zero cross-contamination;
- reconciliation invariant holds on a fixed campaign of ≥500 games with
  invalid-run rate below a declared threshold (target <2%);
- the report reproduces byte-identically from the SQLite DB.
This campaign is the baseline that all Phase 2 claims measure against.

### Phase 2 — Raise the floor (iterative, hypothesis-driven)
Candidate work items, each a *hypothesis* until measured under §8: minimal
spellcasting for caster backgrounds (share of pool computed from the pinned
manifest, not assumed); special species handling (Felid no-weapon plans,
Mummy no-potion planning, Gnoll training skip, Djinn HP-casting, Formicid
escapes, Demigod goals); god-policy extensions. Each ships behind a config
flag and is validated per the experiment protocol.
**Exit:** baseline-relative improvements with pre-declared minimum effects
and confidence bounds on held-out seeds (e.g. "rune-rate +X pts CI-excluding
zero"). A first random-combo win is reported as an event, never used as a
gate.

### Phase 3 — Experimental layers (deferred by design)
LLM strategic advisor (config-knob adjustments between levels/games; subject
to a fresh §7 audit — postmortem knowledge must not leak into live play on
evaluation seeds); webtiles spectating; own-bot track. None of these
influence the core design beyond the narrow adapter interface in §5.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| qw incompatible with some random combos on the pinned crawl | Phase 0 canaries; per-status buckets in reports; failures become Phase 2 items |
| Telemetry define doesn't work as expected | Phase 0 gate with explicit fallback to reduced metric set (§6) — decided by test, not assumption |
| Undocumented `-list-combos` changes/breaks | Pin-tested; manifest archived, so the sampler never depends on it at run time |
| Long-tail hangs across ~hundreds of combos × many games | Progress-based detection, turn budgets, forced-failure drills (Phase 1 exit) |
| Evaluation overfits campaign data | Holdout seeds, pre-declared analysis, fresh-seed confirmation (§8) |
| Wall-clock effects contaminate results | In-game turn budgets for metrics; wall time as circuit breaker only (§6) |
| Fairness regressions as adapters are added | §7 contract + probe tests; per-adapter re-audit |
| clua memory/CPU limits | `-lua-max-memory 128 -no-throttle` (qw's documented requirements) |

Open questions (defaults chosen, flagged for review):
1. Sampling: uniform over pairs (default) vs. uniform over species-then-
   background. Uniform-over-species doubles the weight of restricted species.
2. Lexicographic objective (§1): is rune-first the right ordering, or should
   score lead?
3. LLM layer (Phase 3): in scope at all, or symbolic-only?

---

## 11. Appendix: sources

Primary: github.com/crawl/crawl (`l-you.cc`, `l-moninf.cc`, `l-view.cc`,
`l-item.cc`, `l-crawl.cc`, `newgame.cc`, `main.cc`, `hiscores.cc`,
`docs/options_guide.txt`, `AppHdr.h`/`hiscores.cc` for `DGL_MILESTONES`);
github.com/crawl/qw (source, `qw.rc`, `make-qw.sh`, `util/`, docs) and
github.com/elliptic/qw. Ecosystem: dcss-api, dcss-ai-wrapper (+ arXiv
1902.01769), nkhoit/dcss-ai. LLM evidence (secondary): BALROG (arXiv
2411.13543), NetPlay (arXiv 2403.00690), NetHack Challenge/AutoAscend.

Review provenance: `review/REVIEW_PACKET.md` (verification ledger),
`review/SELF_REVIEW.md` (author findings), `review/INDEPENDENT_REVIEW.md`
and `review/REVIEW_SYNTHESIS.md` (independent reviewer; source-verified the
`DGL_MILESTONES` and native-`fully_random` corrections adopted above).
