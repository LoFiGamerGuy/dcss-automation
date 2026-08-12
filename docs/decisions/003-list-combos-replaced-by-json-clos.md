# 003 — `-list-combos` doesn't exist on the pin; use/add JSON CLOs instead

**Date:** 2026-08-12
**Status:** accepted

## Context

`PLAN.md` §2/§9 calls `-list-combos` "an undocumented-but-real flag that
emits pairs only" and flags it explicitly as **pin-tested, not assumed** (§9
Phase 0, §4's risk table: "Undocumented `-list-combos` changes/breaks →
pin-tested; manifest archived, so the sampler never depends on it at run
time"). It doesn't survive contact with the pinned commit
(`a7cece93`/`0.32-a0`): there is no `-list-combos` anywhere in
`crawl-ref/source` (`grep -rn "list-combos"` — zero hits, and the
`commandline_option_type` enum / `cmd_ops[]` string table in `initfile.cc`
have no matching entry). This is exactly the failure mode PLAN.md's own risk
table anticipated, so this is the pin-tested fallback, not a plan violation.

## What exists instead

`initfile.cc` does have `-playable-json` (`CLO_PLAYABLE_JSON`, dispatches to
`playable_metadata_json()` in `playable.cc`), which emits
`{ "species": [...], "jobs": [...], "combos": [...] }` — the species×job
legal-pair manifest §2 point 1 needs, in a strictly better form than a
hypothetical `-list-combos` (structured JSON, not a line format to parse,
and includes aptitudes/modifiers as a bonus). No source patch needed for
this half.

There is **no** existing flag for §2 point 3 (per-combo starting weapon
option sets — `-playable-json` explicitly does not cover this, per its own
doc comment). The weapon-choice logic (`_get_weapons()` in `newgame.cc`) is
`static` to that file, used only by the interactive chargen UI, and is fully
computable from public functions (`job_has_weapon_choice`,
`job_gets_good_weapons`, `starting_weapon_upgrade`, `weapon_restriction` —
the last is explicitly documented as using only `ng.species`/`ng.job`, no
live game state) plus one internal table (the seven candidate base weapons
in `_get_weapons`).

## Choice

Added `-weapon-json` as a new CLO, mirroring `-playable-json`'s exact
pattern: `patches/crawl/0001-weapon-json-clo.patch` adds `CLO_WEAPON_JSON`
next to `CLO_PLAYABLE_JSON` in the enum, `cmd_ops[]`, and
`clo_headless_ok`, dispatches to a new `weapon_metadata_json()` in
`playable.cc` that reimplements `_get_weapons()`'s loop (same candidate
array, same three function calls) without touching `newgame.cc`'s
interactive UI code at all — lower risk than un-`static`-ing the original.
Output: one JSON object per weapon-choice combo (`job_has_weapon_choice` —
229 of the 640 playable combos), each listing exactly the weapon names the
in-game menu would offer.

This extends decision 002's overlay-patch mechanism (`patches/qw/*.patch`)
to crawl itself (`patches/crawl/*.patch`), applied by the same
`ops/fetch-vendor.sh` after checkout. `-playable-json` needed no patch, so
until now there was no crawl-patch precedent; 002's reasoning (diffable,
disposable-`vendor/`-compatible) applies identically here.

## Two bugs found and fixed while building this (both real, both would have
produced a silently-wrong manifest, not a crash)

1. **`weapon_base_name()` needs `init_properties()` first.** `-weapon-json`
   (like `-playable-json`) can be dispatched from `main.cc`'s early
   `parse_args(argc, argv, /*rc_only=*/true)` pass, which runs *before*
   `init_properties()` populates the `Weapon_index`/`Weapon_prop` lookup
   tables. Without it, every weapon name silently resolved to whatever sits
   at table index 0 ("club") — no crash, no warning, just wrong data for
   every combo. Fixed by calling `init_properties()` (idempotent — it only
   refills static tables) at the top of `weapon_metadata_json()`.
2. **`WPN_UNARMED` isn't a `Weapon_prop` entry.** It's not a physical
   weapon, so `weapon_base_name(WPN_UNARMED)` hit the same index-0 fallback
   and printed "club" for the unarmed option on every single combo (229/229
   — an exact-match signature that made this easy to spot once looked for).
   `newgame.cc`'s own interactive menu special-cases this
   (`defweapon == WPN_UNARMED ? "unarmed" : weapon_base_name(defweapon)`);
   mirrored the same check in `weapon_metadata_json()`.

## Validation

- `-playable-json`: 34 species, 25 jobs, 640 combos.
- `-weapon-json`: 229 combos with a weapon choice, all with non-empty
  weapon lists after the two fixes above.
- Cross-check independent of both CLOs: the set of jobs appearing in
  `-weapon-json` output (`{Berserker, Chaos Knight, Cinder Acolyte, Delver,
  Fighter, Gladiator, Monk, Reaver, Warper}`, 9 jobs) matches exactly the
  set of jobs with `WCHOICE_PLAIN`/`WCHOICE_GOOD` in `job-data.h`, read
  directly off the source table rather than through either new/existing CLO.
- Verified the patch applies cleanly to a **fresh** `ops/fetch-vendor.sh`
  checkout (not just the already-edited working tree) and rebuilds
  successfully — the actual "reproducible build from lock info on a clean
  machine" acceptance test.

## Consequences

- The legal-character manifest (Phase 0 deliverable) is generated from
  `-playable-json` + `-weapon-json` together, not a single `-list-combos`
  call. `docs/manifests/README.md` (or equivalent) should say so explicitly
  so a future session doesn't go looking for a flag that isn't there.
- If crawl upstream ever adds a real `-list-combos` or an equivalent weapon
  CLO, our patch becomes redundant and can be dropped in favor of upstream
  — but only as a deliberate re-pin decision (versioned per PLAN.md §3), not
  silently.
