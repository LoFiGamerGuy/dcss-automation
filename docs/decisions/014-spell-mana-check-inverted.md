# 014 — caster underperformance root cause: qw's spell-affordability check is inverted

## Context

The Phase 1 exit review's `by_archetype` stratification (`data/phase1-500-report.json`)
showed casters — 214/500 (42.8%) of the sampled population, by far the
largest archetype bucket — dead last on every outcome axis: median score
**8** (vs. 44 melee, 109 hybrid, 27 utility), median XL **2** (vs. 3-4),
median turns survived **330** (vs. 1299-2589). Session 4's journal entry
flagged this as the highest-leverage remaining Phase 2 candidate (largest
population share of any candidate on PLAN.md's list) and queued reading
`vendor/qw/source/plans-spells.lua` — qw's actual spellcasting logic — as
the first step, rather than assuming "casters played as weak melee" (PLAN.md
line ~144) means qw has no spellcasting logic at all.

## Investigation

`plans-spells.lua` (87 lines total, confirmed via grep to be the *only* file
in `vendor/qw/source/*.lua` mentioning spells, memorisation, or spellbooks —
qw has zero book-reading/spell-learning logic anywhere; its only spell
behavior is casting one fixed starting spell) has:

- `get_starting_spell()`: picks one attack spell the character already
  starts memorised with, from a fixed list (`Foxfire`, `Freeze`,
  `Magic Dart`, `Necrotise`, `Sandblast`, `Shock`, `Sting`,
  `Summon Small Mammal`). Called once, at game start, into `qw.starting_spell`
  (`init.lua:161`) — never recomputed.
- `plan_starting_spell()`: the first entry in the attack cascade
  (`plans-attack.lua:511`, ahead of melee/throwing/wands), gated by
  `spell_castable(qw.starting_spell)`.

`spell_castable(sp)` (`plans-spells.lua:27-46`):

```lua
function spell_castable(sp)
    if you.silenced()
            or you.confused()
            or you.berserk()
            or in_bad_form()
            or can_use_mp(spells.mana_cost(sp)) then
        return false
    end
    ...
    return true
end
```

`can_use_mp(mp)` (`player.lua:411-419`) is `you.mp() >= mp` (or, for a
Djinni, `you.hp() > mp`) — **true means "can afford it."** Every other call
site in the codebase uses it in that positive sense to *permit* an action
(`religion.lua`'s eight ability gates all read `and can_use_mp(cost)`:
proceed only when affordable). `spell_castable`'s `or can_use_mp(...)` term
is backwards: it's inside an `if X or Y or ... then return false` guard, so
the function declares the spell **not castable exactly when the player can
afford to cast it**, and — since a false `can_use_mp` doesn't trigger the
early return — falls through to `return true` ("castable") precisely when
the player **cannot** afford it. `spell_castable` has exactly one caller
(`plan_starting_spell`, grepped project-wide), so this isn't a case of one
correct and one buggy use of the same helper — it's simply backwards at its
only call site.

Net effect for the whole game: a caster's one attack spell is blocked
whenever they have the mana to cast it (which, early game with a small MP
pool topped up between fights, is most of the time), and "permitted"
exactly when they can't afford it — at which point `magic("z" .. letter ..
"f")` either fails outright or wastes the action, and the attack cascade's
next entries (`plan_poison_spit`, `plan_targeted_evoke`, `plan_throw`,
`plan_launcher`, `plan_melee`) take over. Casters, whose job design assumes
their spell is the primary damage source and who are correspondingly weak
in melee/throwing/launcher skills, end up fighting almost entirely with
whatever's left after that fallback — matching the measured outcome exactly:
weak damage, slow XL gain, short survival. This is a single inverted
boolean, not a design gap requiring new spell-learning AI (which would be a
much larger, out-of-scope feature per decision 011's "this project runs a
stock qw ... as a fixed baseline" framing) — the existing one-spell logic
just needs to actually run when it's supposed to.

## Fix

Minimal call-site guard, same shape as decisions 011/012
(`vendor/qw/source/plans-spells.lua`):

```lua
function qw_spell_uncastable_for_mana(sp, affordable)
    if affordable == nil then
        affordable = can_use_mp(spells.mana_cost(sp))
    end
    if QW_BUGFIX_SPELL_MANA_CHECK == false then
        return affordable
    end
    return not affordable
end
```

`spell_castable`'s `or can_use_mp(spells.mana_cost(sp))` term is replaced
with `or qw_spell_uncastable_for_mana(sp)`. `can_use_mp` itself is untouched
(it's correct everywhere else it's used — `religion.lua`, `plans-abyss.lua`).
`affordable` takes an optional explicit override, same reasoning as decision
012's `qw_transform_is_indefinite(transform_name)`: a regression test can
drive both the "affordable" and "not affordable" branches directly, without
needing to actually be in either MP state in a real game.

### Config flag

Per PLAN.md §8/Phase 2, gated by a new rc-settable global,
`QW_BUGFIX_SPELL_MANA_CHECK` (`campaign.rc.tmpl`, threaded through
`ops/rc-gen.py`'s `write_run_dir(..., bugfix_spell_mana_check=True)`,
`ops/runner.py`'s `run_game(..., bugfix_spell_mana_check=True)`,
`ops/campaign.py`'s `--disable-bugfix-spell-mana-check` CLI flag, and a new
`bugfix_spell_mana_check` column in `ops/collector.py`'s schema). Default/
unset behaves as `true` (fixed). A separate flag from `QW_BUGFIX_LUA_ERRORS`
and `QW_BUGFIX_INDEFINITE_TRANSFORM`: independent hypothesis, and this fix
touches a different file/function than either of the other two.

## Verification

`ops/bugfix-spell-mana-test.py`, same wizard-mode dlua console choreography
as decisions 011/012's drill tests (`&`, confirm, Ctrl-U, `expect()` each
prompt's exact text): calls `qw_spell_uncastable_for_mana(sp, affordable)`
directly against the real pinned+patched binary with an explicit
`affordable` override —

- flag on (fixed): `affordable=true` → `false` (castable, not blocked);
  `affordable=false` → `true` (correctly blocked, can't afford).
- flag off (reproduces the original bug): `affordable=true` → `true`
  (wrongly blocked — the exact bug); `affordable=false` → `false` (wrongly
  "castable" while unaffordable — the exact bug).

## Alternatives considered

- **Flip the boolean in place (`or not can_use_mp(...)`) with no named
  helper function** was rejected in favor of a named guard function, purely
  for testability: decisions 011/012 both introduced a named function
  specifically so a drill test can call it directly through the wizard
  console without needing to reach the exact game state (low/full MP,
  Makhleb worship, a beast-form transform) that would otherwise be required
  — the same reasoning applies here.
- **A population-wide fix in `can_use_mp` itself** was never on the table:
  `can_use_mp` is correct (`religion.lua`'s eight call sites all read it in
  the intended positive sense) — the bug is entirely local to
  `spell_castable`'s one call site.

## Follow-up

A pre-declared Phase 2 experiment (`data/experiments/caster-spell-mana-fix/`)
measures the fix's actual population-wide effect (the population-wide
`xl_at_least_3_rate`, not a caster-only metric, matching decisions 011/012's
methodology of measuring the *population-wide* symptom rate rather than
filtering to the affected subpopulation) on held-out validation seeds
against the frozen phase1-500 baseline, per PLAN.md §8. Baseline
(`data/phase1-500.db`): overall `xl_at_least_3_rate` 232/500 = 46.4%; caster
archetype alone 61/214 = 28.5% (vs. hybrid/melee/utility all well above
that) — the gap this fix targets.
