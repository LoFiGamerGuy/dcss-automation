# 012 — quit_stuck root cause: qw rests forever in an indefinite talisman form

## Context

The phase1-500 baseline campaign recorded 28/500 (5.6%) runs as
`quit_stuck` (the harness's progress-based hang detector force-quitting a
game). All 28 shared one background: **Shapeshifter** — and every single
Shapeshifter game in the campaign (28/28) ended this way. That's not a rare
edge case within a bucket; it's a completely dead character-creation
background, worth fixing on the same "raise the floor" grounds as decision
011's `lua_error` items.

## Investigation

Shapeshifter starts the character already transformed into `beast-form` via
an equipped talisman (0.32-a0's talisman system), with no weapon and no
spells (`vendor/crawl/crawl-ref/source/form-data.h`'s `transformation::beast`
entry). Every sampled Shapeshifter run (`data/runs/phase1-500-*`, e.g.
`phase1-500-000015`, `-000028`, `-000047`, `-000053`, `-000054`) shows the
identical signature regardless of species or the D:1 vault rolled: turn
counter races to 8000-9000 while wall-clock stays ~17-30s (many cheap
no-op-ish actions per real second), 0 kills, still on D:1, still in
`beast-form`, ending via the 0.32 "power of Zot" camping-punishment
mechanic (repeated "Touched by the power of Zot" max-HP drain from staying
in one place too long) draining HP to the harness's hang threshold.

Root cause, confirmed by reading qw's and crawl's source directly:

- `transformed()` (`vendor/qw/source/player.lua:320-322`) is
  `you.transform() ~= ""` — true for *any* active transformation, with no
  distinction between a temporary spell-form (expires on its own) and an
  indefinite one.
- `you.transform()` (`l-you.cc:387-388` → `transform_name()` →
  `form-data.h`'s `wiz_name` field) returns `"beast"` for the entire game for
  a beast-talisman Shapeshifter — this form only ends via the player's own
  "Begin Untransformation" ability, so `transformed()` never goes false on
  its own.
- `reason_to_rest()` (`plans-rest.lua:90`, formerly `plans-rest.lua:89`) and
  `should_rest()`'s orb-carrying branch (`plans-rest.lua:51`, formerly `:50`)
  both include a bare `or transformed()`. With `transformed()` permanently
  true, `should_rest()` (`plans-rest.lua:44-67`) is permanently true.
- `plans.rest` sits ahead of `plans.explore`/`plans.explore2` in the master
  cascade (`plans.lua:141-155`, built by `initialize_plan_cascades()` at
  `plans.lua:126-137`). Once `should_rest()` fires, `plan_long_rest()`
  (`plans-rest.lua:138-145`) calls `long_rest()` → `magic("5")`
  (`"5"` = `CMD_REST`, crawl's rest-and-long-wait command) every tick,
  forever — `plans.explore`/`explore2` are never reached.

This is a logic gap, not a caught Lua error (no exception involved, unlike
decision 011's two bugs) — a missing distinction between "transformed with
a duration that will lapse soon, worth waiting out" (the case `transformed()`
was written for — see its correct uses elsewhere: `plans-spells.lua:31`,
`plans-stairs.lua:184`, `move-flee.lua:63/215`, `move-tactics.lua:117`, all
genuinely-transient forms) and "transformed indefinitely, waiting will never
end" (talisman forms).

`form-data.h` names 9 talisman-driven forms (`talisman_type` other than
`NUM_TALISMANS`): `blade` (`TALISMAN_BLADE`), `statue`, `snake`
(`TALISMAN_SERPENT`'s wiz_name), `dragon`, `death`, `storm`, `beast`, `maw`,
`flux`. All other forms (`spider`, `bat`, `pig`, `appendage`, `tree`,
`porcupine`, `wisp`, `jelly`, `fungus`, `shadow`, `hydra`) are spell-driven
and expire on their own. This isn't Shapeshifter-specific: any character
who transforms mid-game via one of these 9 talismans (or, in principle, a
future permanent-transform item) would hit the identical trap the moment
they transform and don't self-untransform — the fix keys off "is this
transform indefinite," not "is the background Shapeshifter."

## Fix

Minimal call-site guard, same shape as decision 011's two fixes
(`vendor/qw/source/plans-rest.lua`):

```lua
function qw_transform_is_indefinite(transform_name)
    transform_name = transform_name or you.transform()
    local indefinite_forms = {
        blade = true, statue = true, snake = true, dragon = true,
        death = true, storm = true, beast = true, maw = true, flux = true,
    }
    return indefinite_forms[transform_name] or false
end

function qw_transformed_worth_resting_for()
    if QW_BUGFIX_INDEFINITE_TRANSFORM == false then
        return transformed()
    end
    return transformed() and not qw_transform_is_indefinite()
end
```

`reason_to_rest()`'s and `should_rest()`'s `or transformed()` clauses are
replaced with `or qw_transformed_worth_resting_for()`. `transformed()`
itself is untouched (it's correctly used elsewhere for its original,
transient-form meaning) — only the two rest-trigger call sites change.
`qw_transform_is_indefinite` takes an optional explicit `transform_name`
override, for the same reason decision 011's `qw_equip_slot_or_empty` takes
`cur_equip` explicitly: a regression test can drive it by name without
having to actually be transformed in-game.

### Config flag

Per PLAN.md §8/Phase 2, gated by a new rc-settable global,
`QW_BUGFIX_INDEFINITE_TRANSFORM` (`campaign.rc.tmpl`, threaded through
`ops/rc-gen.py`'s `write_run_dir(..., bugfix_indefinite_transform=True)`,
`ops/runner.py`'s `run_game(..., bugfix_indefinite_transform=True)`,
`ops/campaign.py`'s `--disable-bugfix-indefinite-transform` CLI flag, and a
new `bugfix_indefinite_transform` column in `ops/collector.py`'s schema).
Default/unset behaves as `true` (fixed). A separate flag from
`QW_BUGFIX_LUA_ERRORS` since this isn't a Lua-crash fix and the two are
independent hypotheses — a bug in one doesn't imply anything about the
other, and the existing lua-error-bugfix experiment's control arm should
keep reproducing exactly its own two crashes, not also this stall.

## Verification

`ops/bugfix-indefinite-transform-test.py`, same wizard-mode dlua console
choreography as decision 011's drill test (`&`, confirm, Ctrl-U, `expect()`
each prompt's exact text): calls `qw_transform_is_indefinite(name)` directly
by name against the real pinned+patched binary — `"beast"`/`"flux"` (talisman
forms) → `true`; `""`/`"spider"` (no transform / a spell form) → `false`;
confirmed both with the flag on and off (the flag only gates
`qw_transformed_worth_resting_for()`, not the classifier itself). **5/5
drills pass.**

## Alternatives considered

- **A hardcoded `you.transform() == "beast"` check** (only the Shapeshifter
  case actually observed) was rejected in favor of the full 9-form
  indefinite-forms table: the bug's mechanism is general to any indefinite
  transform, and `form-data.h` names all 9 explicitly, so there's no reason
  to under-guard and wait for a Flux Shapeshifter or a mid-game talisman use
  to reproduce the same class of stall later.
- **Checking `you.duration()` for a transformation timer** instead of a
  name table was investigated and rejected: crawl's Lua bindings
  (`l-you.cc`) expose no generic `you.duration(name)` or talisman-status
  accessor, and the specific `DUR_TRANSFORM`-style durations aren't bound
  either — a name-table lookup against the fixed, small set of talisman
  `wiz_name`s is the only mechanism actually reachable from qw's Lua
  environment, and matches the project's existing bias toward minimal,
  reachable guards over larger new bindings.

## Follow-up

A pre-declared Phase 2 experiment (`data/experiments/indefinite-transform-bugfix/`)
measures the fix's actual effect on the `quit_stuck` rate on held-out
validation seeds against the frozen phase1-500 baseline, per PLAN.md §8.
