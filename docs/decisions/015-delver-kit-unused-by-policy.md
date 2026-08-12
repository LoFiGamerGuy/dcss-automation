# 015 — Delver's signature kit is structurally invisible to qw's policy (characterization, not yet a fix)

## Context

Session 6's journal entry flagged Delver (background, n=23/500=4.6% of the
phase1-500 sample) as the next Phase 2 candidate after caster-spell-mana-fix:
score median 0 (tied worst in the baseline), XL median 1, turns-survived
median 60, and — unlike every other flagged cluster so far (011, 012, 014) —
**0% of its 23 runs are `lua_error`/`quit_stuck`/any abnormal status**, all 23
are clean `died`, with varied organic-looking death causes (jellies, orc
wizards, hounds, several early uniques). That session queued a source read of
qw's planner before concluding bug-vs-intentionally-fragile. This entry is
that source read, done read-only while the machine was occupied by the
indefinite-transform-bugfix treatment-arm retry campaign (no new crawl
processes spawned).

## Delver's starting kit (`job-data.h:124-132`)

Species pool: Felid, Spriggan, Kobold, Vampire, Gnoll — small/fragile species.
Stats 4/2/6 (Str/Int/Dex) — a stealth/dodge build, not a Str-melee one.
Skill priority: Stealth 5 (highest), Dodging 2, Fighting 3, Weapon 2.
Aptitudes and kit both signal an evasion/utility playstyle, not straight
melee. Starting items: leather armour, **scroll of fog**, **scroll of
revelation**, **scroll of fear**, **potion of haste**, **wand of digging
charges:3**, `weapon_choice::plain`.

## What qw's policy actually does with each item (grepped project-wide, not assumed)

- **potion of haste** — fully used. `plan_haste`/`can_haste`/`want_to_haste`
  (`plans-emergency.lua:378-736`) is a generic cascade entry, triggers on
  high-threat or a scary-enemy primary attack. Not a gap.
- **wand of digging** — partially used, but only in the *opposite* direction
  Delver's kit seems to imply. Every reference (`plans-emergency.lua:1017`
  `plan_dig_grate`, `plans-stuck.lua:76` `plan_stuck_dig_grate`,
  `plans-zig.lua:75` `plan_zig_dig`, `monsters.lua:590`
  `should_dig_unreachable_monster`) digs *toward* an enemy to reach it through
  a grate, or is Zig-scoped. No plan digs *away* from danger to escape. Not
  Delver-specific — this is qw's only digging behavior for any background.
- **scroll of fog** — used, but gated to a single, narrow context:
  `plan_zig_fog` (`plans-zig.lua:4-15`) opens with
  `if not in_branch("Zig") ... then return false end` — hard-gated to the
  Ziggurat portal specifically. Outside Zig it is never read for its escape
  value, no matter how low HP or how many enemies are in LOS. Delver runs
  die at median turn 60 / XL 1 — nowhere near a Zig entry (needs a rune first)
  — so for the entire population of Delver deaths sampled, this item is dead
  weight. Confirmed via `want_scroll`'s `items.lua:117-128` pickup-priority
  list too: `"fog"` is only added to the wanted set when
  `qw.planning_zig`, so even *replacing* a used/lost one outside Zig context
  wouldn't happen.
- **scroll of revelation** — grepped case-insensitive across every `.lua`
  file in `vendor/qw/source/`: **zero matches, anywhere.** Not read, not
  evaluated, not in any wanted-item list. Structurally inert.
- **scroll of fear** — same grep, same result: **zero matches, anywhere.**
  Also structurally inert.

Unidentified-scroll reading (`plans-items.lua:637-670`,
`read_unided_scroll`/`plan_read_unided_scrolls`) doesn't rescue fear/
revelation either — starting-kit items are already identified by name from
character creation, so they never enter the "read to identify" path.

## Assessment

3 of Delver's 5 signature non-armour kit items (fog outside Zig, revelation,
fear — 60% of the deliberately-chosen kit) have no behavioral value in qw's
current policy; only haste (generic) and digging (generic, wrong direction
for this kit's apparent intent) do anything. Stealth training (skill
priority 5, the class's single highest-priority skill) has a passive
in-engine effect (reduces monster noticing) regardless of bot logic, so it
"works" without any dedicated plan — but qw has no active stealth-preserving
behavior (e.g. avoiding waking sleeping monsters, preferring routes that stay
out of LOS) beyond whatever falls out of its general explore/combat logic, so
the passive benefit alone doesn't compensate for a fragile species pool
fighting essentially as underequipped plain melee.

This is not a crash/error bug like 011/012/014 — nothing misfires, it simply
never fires. It matches PLAN.md's general Phase 2 framing (species/background
combinations whose designed playstyle the bot doesn't implement) rather than
a single inverted-condition bug. Death causes being varied/organic (not one
crash signature) is exactly consistent with this: Delvers are dying to normal
early threats *because* their differentiated escape/utility tools never
engage, not because of a code fault.

## Decision: characterize now, fix later (deferred — not blocked)

Per this project's established discipline (011/012/014 all built the fix +
drill + predeclared experiment together, in one working session, against a
live binary) — a Delver fix is **not implemented in this entry**. The machine
is currently saturated by the indefinite-transform-bugfix treatment-arm retry
campaign (16/16 workers), and this project's standing practice (reaffirmed
across sessions 3-6) is not to run additional crawl-spawning work
concurrently with an active campaign. Writing an untested behavioral Lua
change without the ability to drill-test it immediately would violate the
"don't build the classifier and defer testing it" principle from Phase 1.

**Candidate fix shape for a future session** (not yet written): generalize
`plan_zig_fog` into a `plan_fog_escape`-style cascade entry usable outside
Zig — gated on the same `hp_is_low(...)`/`qw.danger_in_los`/enemy-count
conditions already proven in the Zig version, minus the `in_branch("Zig")`
check — plus a new `plan_fear`-style entry that reads scroll of fear against
a single dangerous/scary enemy (mirroring `want_to_haste`'s `scary_enemy`
branch shape in `plans-emergency.lua:713-736`) rather than inventing a new
threat-assessment pattern from scratch. Both should go behind their own
`QW_BUGFIX_*`-style rc flag per this project's established config-flag
convention (011/012/014), be added to `plans.emergency`'s cascade
(`plans-emergency.lua:1033-1083`) at a sensible priority (likely near
`plan_zig_fog`'s current slot, before `plan_flee`), and get a wizard-mode
drill (mirroring `ops/bugfix-spell-mana-test.py`) plus a predeclared
experiment on the population-wide symptom this project's methodology favors
(`xl_at_least_3_rate` or similar, not a Delver-only metric) before being
trusted.

## Next step for whoever picks this up

Once the machine is free (no active campaign): read `plans-emergency.lua`'s
full `assess_enemies()`/`scary_enemy` logic once more closely (only skimmed
here) to reuse its threat classification rather than re-deriving one, write
the two new plan functions + rc flags + drill test, predeclare an experiment
(new seed pool disjoint from all four prior experiments' ranges — next
available block is `6000000..6009999`), and run it the same one-arm-per-
`setsid`-launch way decision 013 established as the *only* reliably clean
launch pattern for this project's experiments.
