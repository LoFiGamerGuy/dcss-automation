# Author's self-review of PLAN.md

This is the authoring session's own critical review of `PLAN.md`, produced
after the plan was written. It is placed here so an independent reviewer can
compare notes **after** completing their own review — do not read this before
finishing an independent pass, to avoid anchoring.

Line references are into `PLAN.md` at the repository root (the same text is
embedded verbatim in `review/REVIEW_PACKET.md` §2). Claims marked "verified"
were checked against clones of github.com/crawl/qw and fetched files from
github.com/crawl/crawl; see the verification ledger in REVIEW_PACKET.md §3.

Overall verdict: the architecture is technically feasible and the
qw-plus-harness choice is sound, but the plan has one genuine goal/design
contradiction, one internal version inconsistency, and several places where
the evaluation methodology needs tightening before execution.

## High

**H1. The "completely random character" claim contradicts the recommended
defaults — the sampler as specified is not unbiased.** Lines 3–4 promise "any
legal species × background × weapon," but lines 276–278 default weapon choice
to "sensible starting weapon per combo (hypercombogen style)" — and
hypercombogen's mapping is opinionated (Fighters/Gladiators get waraxes,
Merfolk tridents, etc.; verified in qw's `util/hypercombogen.sh`), which is
curation, not randomness. Additionally, nothing validates that the harness's
combo enumeration matches the game's own legal set; lines 178–180 gesture at
`fully_random = true` as a "purity check" but never define the check. The
plan needs an explicit **randomness contract**: which dimensions are
randomized (species, background, weapon — noting Draconian color is assigned
by the game at XL7 regardless), over what distribution (uniform over legal
combos), and a concrete validation step (diff the sampler's universe against
`-list-combos` output at Phase 0). If weapons stay curated by default, the
plan should say plainly that v1 randomizes the combo but not the weapon — or
flip the default.

**H2. Internal inconsistency: species facts are from 0.34/trunk, but the
architecture pins crawl to 0.32-a0.** Lines 70–76 describe the "current game"
pool including Poltergeist (added in 0.33), while design decision 1 (lines
167–171) pins crawl to qw master's target, 0.32-a0 — where
Poltergeist/Revenant don't exist and Armataur still does. The actual combo
pool is defined by the *pinned* version, not trunk. This sets reviewer
expectations for which pathological species Phase 2 must handle. The plan
should state that the pool, counts, and special-species list are re-derived
from the pinned binary at Phase 0.

## Medium

**M1. Phase 2 exit criteria are unsupported absolute targets (lines
244–245).** "Median random-combo game reaches Lair; ≥10% reach a rune" has no
baseline behind it. qw's *best* combos have low win rates, and roughly half
the random pool will be casters played as bad melee — the median game
plausibly dies well before Lair even after improvements. Make the targets
relative to the Phase 1 baseline (e.g., "+50% rune-rate vs. baseline") and
set absolute numbers only after the first campaign.

**M2. The A/B methodology overstates what `-seed` controls (lines 242–243).**
Seeding fixes dungeon generation, not action/combat RNG, and any behavioral
change diverges the trajectory immediately — so same-seed A/B gives shared
maps, not paired outcomes. The comparison is still valid but needs
sample-size framing: campaigns must be sized for statistical power on
rune-rate deltas, which at low base rates means hundreds of games per arm.

**M3. The milestone data source is unverified (lines 19–28, 153, 270).** The
collector assumes local crawl writes a `milestones` file. qw's `batch-qw.sh`
deletes one (verified), which is suggestive, but whether a plain non-DGL
`make` build emits milestones (vs. requiring a build define) is unconfirmed —
and the plan's own risk table (line 270) relies on "logfile/milestones"
without noting this. Add a Phase 0 verification item, with the fallback
spelled out: the end-of-game logfile line (`place`, `urune`, `xl`, `sc`,
`tmsg` fields) is sufficient for the milestone ladder if the milestones file
is absent. Also note the ladder at lines 19–21 is a partial order, not a
sequence — extraction should record the *set* of milestones hit, not assume
ordering.

**M4. Failure-mode handling is too thin for the fleet (lines 186–190).** The
most common qw failure is not a crash but a **Lua error that leaves crawl
paused at an input prompt** — a wall-clock timeout eventually catches it but
burns a worker slot for the full timeout, and the plan doesn't capture the
error for triage. Add: progress-based hang detection (no save/logfile mtime
change in N minutes), capture of crawl's message log/stderr on abort, an
explicit abandon-vs-resume policy (qw has `reset_coroutine`), and
per-instance `-name`/directory uniqueness for parallel runs.

**M5. No throughput or compute budget (lines 169, 225).** "qw finishes games
in minutes of wall-clock" is asserted, not measured, and drives the
feasibility of the 500–1,000-game Phase 1 campaign, timeout values, and
parallelism. Add a Phase 0 measurement (median/p95 wall-clock per game, CPU
per instance) and derive the campaign budget from it.

**M6. "~40% of the combo pool" casters (line 232) is an unsupported
estimate.** Count it from the pinned version's background list and cite the
number.

## Low

**L1. Hidden-information leakage — the answer is "no, by construction," but
the plan never says so.** clua exposes only player-knowledge (monster info
objects mirror the UI — damage *bands* not exact HP, no unseen
monsters/cells; item info is identification-gated; verified in
`l-moninf.cc`/`l-item.cc`), and campaigns run non-wizard, so the recommended
path is fair. Two residual channels deserve a sentence each: (a) `c_persist`
carries memory across games — harmless with random seeds, but combined with
M2's fixed seed lists it could leak dungeon-layout knowledge between games on
the same seed; clear it between games or don't reuse seeds within a campaign;
(b) wizard mode is a leak vector and is already excluded from metrics runs
(lines 279–281) — make that a rule, not a default.

**L2. `-list-combos` is undocumented (lines 65, 292).** Verified real (qw's
hypercombogen.sh calls it) but it's absent from crawl's `-help` output, so
it's an unstable interface across versions — pin-and-test, and the appendix's
implication that it's documented in `main.cc` help is inaccurate.

**L3. The ~15% win-rate figure (line 31) is from a since-removed species
(Deep Dwarf) in offline testing.** It's flagged in the document's footnote,
but the sentence reads like a current benchmark; qualify it inline.

**L4. Combo count precision (line 70).** 27×26 = 702 *nominal*; the legal
count is meaningfully lower after bans (Felid excludes all weapon-dependent
backgrounds, Demigod excludes zealots). Say "legal count enumerated via
`-list-combos` at Phase 0."

**L5. Unnecessary weight in vendoring (lines 201–202).** A crawl submodule
drags a very large repo into every clone; a pinned shallow clone in
`build-crawl.sh` is lighter. Likewise consider a fork of qw (rebaseable)
instead of a `patches/` overlay — patch stacks over 19k lines of Lua rot
quickly.

## Suggested focused edits (not yet applied)

1. §2.2/§4.2: add a "Randomness contract" subsection — dimensions randomized,
   uniform-over-legal-combos, Phase 0 validation against `-list-combos`, and
   an honest statement about the weapon-curation default (H1).
2. §2.2: re-scope species/combo facts to "as of the pinned version,
   re-derived at Phase 0" (H2, L4).
3. §5 Phase 2: replace absolute exit criteria with baseline-relative ones
   (M1).
4. §5 Phase 2 / §6: add a sentence on seed semantics and campaign sizing for
   A/B power (M2).
5. §5 Phase 0: add verification items — milestones-file presence in local
   builds, `-list-combos` behavior, per-game wall-clock measurement (M3, L2,
   M5).
6. §4 decision 4: expand failure handling — progress-based hang detection,
   error capture, reset/abandon policy, per-instance naming (M4).
7. §6: add a short "Fairness" paragraph stating the no-hidden-information
   argument and the `c_persist`/seed-reuse caveat (L1).
8. §4 repo layout: swap the crawl submodule for a pinned shallow clone;
   consider a qw fork over a patch overlay (L5).
