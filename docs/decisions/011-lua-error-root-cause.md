# 011 — lua_error root cause: two real qw upstream bugs, fixed behind an A/B flag

## Context

The phase1-500 baseline campaign (Phase 1 exit review, `710fab8`) recorded
26/500 (5.2%) runs as `lua_error`. That review flagged this as the first
Phase 2 candidate: "reducing lua_error grows the effective sample for every
later experiment." `ops/runner.py`'s classifier only records "matched 'Lua
error' in output" — it doesn't capture *which* error, so the actual qw bug
had to be found by replaying runs and reading qw's source, not guessed at.

## Investigation

Replaying original campaign runs verbatim (same char_seed/game_seed/combo)
does **not** reliably reproduce the same trajectory or the same crash —
confirmed on 5 of the 26 lua_error runs, 2 reproduced the exact same crash
and 3 instead played out to a different, uneventful natural death within
the replay's time budget. qw's own play is evidently not fully determined
by the crawl seed alone (most likely some un-seeded Lua-level tie-breaking
inside qw itself — not root-caused further, out of scope for this item).
This means the *fix* had to be validated at the source level and via direct
console evaluation, not by trying to make the original 26 runs replay
exactly.

Two runs did reproduce, giving two distinct, real error texts:

1. **`phase1-500-000000`** (FeFi.unarmed, char_seed=0): `attempt to index
   local 'cur_equip' (a boolean value)` — `equipment.lua:704` (combined
   `qw.lua:3792`).
2. **`phase1-500-000181`** (AtBr, char_seed=181): `attempt to perform
   arithmetic on global 'hostile_servants_timer' (a nil value)` —
   `plans-rest.lua:48` (combined `qw.lua:14283`).

### Bug 1 — `cur_equip` boolean-index crash

`inventory_equip()` (`equipment.lua`) returns `nil` when a character has
literally zero equipped items — `inventory_equip_func`'s `found_equip` stays
`false` and the function falls off the end returning nothing. Its caller,
`turn_memo_args` (`qw.lua` ~18145), memoizes results in a table keyed by
call args; since a Lua table can't distinguish "not yet cached" from
"cached `nil`", `turn_memo_args` explicitly converts a `nil` result to the
boolean `false` before caching it (see the comment already in that function:
"We turn any nil argument into false..." — the same pattern for return
values). So `cur_equip` in a caller can legitimately be `false`, a boolean,
not just a table or `nil`.

`equip_letter_for_item()` (`equipment.lua:683`) didn't account for this:

```lua
local max_items = slot_max_items(slot)
if max_items == 1
        or not cur_equip[slot]        -- crashes if cur_equip is false
        or #cur_equip[slot] < max_items then
    return ""
end
```

`slot_max_items` returns >1 only for `"ring"` (2, or 8 for Octopode) or
`"weapon"` on a Coglin (2-handed dual-wielding) — every other slot
short-circuits on `max_items == 1` before ever touching `cur_equip[slot]`,
which is why this didn't show up on every zero-equipment character, only
ones being offered a ring or (for a Coglin) a second weapon. An unarmed
Felid — no weapon, most armour slots unusable by species, so genuinely zero
equipped items early on — is exactly the profile that hits it; Felid was
independently the most common species among the 26 lua_error runs (6/26,
per the Phase 1 exit review).

### Bug 2 — `hostile_servants_timer` nil-arithmetic crash

`should_rest()` (`plans-rest.lua:27`) reads a global `hostile_servants_timer`
that is **referenced nowhere else in qw's entire source tree** (grepped all
of `vendor/qw/source/*.lua`) — no assignment, anywhere. It's an orphaned
global, presumably left behind by a removed or renamed Makhleb-ally-timer
feature:

```lua
return you.berserk()
    or you.turns() < hiding_turn_count + 10
    or you.god() == "Makhleb"
        and you.turns() <= hostile_servants_timer + 100   -- always nil
    or reason_to_rest(99.9)
```

Every Makhleb worshipper crashes here, unconditionally, the first time
`should_rest()` runs after joining — this doesn't depend on any particular
game state beyond `you.god() == "Makhleb"` being true, so it isn't a rare
edge case among Makhleb worshippers, it's all of them. (Chaos Knight is a
zealot background that can start worshipping Makhleb, Xom, or Lugonu; the
originally-observed crash was on a Barachi Chaos Knight. Which god a given
Chaos Knight gets is itself one of the non-reproducible details noted
above — not pinned down further since it isn't needed to fix or verify the
bug: any run that ends up worshipping Makhleb hits this, regardless of how
it got there.)

## Fix

Both are genuine upstream qw bugs (not a harness issue), fixed with minimal
guards at the point of use — `patches/qw/0001-fix-lua-errors.patch`,
applied by `ops/fetch-vendor.sh` (the existing overlay mechanism from
decision 002):

- `equipment.lua`: new `qw_equip_slot_or_empty(cur_equip, slot)` returns
  `cur_equip and cur_equip[slot]` instead of indexing directly; the
  crash site now computes this once and reuses it.
- `plans-rest.lua`: new `qw_hostile_servants_timer()` returns
  `hostile_servants_timer or 0` instead of the bare (possibly-nil) global;
  `should_rest()` calls it instead of referencing the global directly. `0`
  is chosen because the surrounding condition is `you.turns() <= X + 100` —
  a timer of `0` means "no active timer", the same effect as the guard not
  firing, which is the closest available reading of what the removed
  feature probably intended before it went dead.

Both fixes are correctly scoped: they change behavior only in the exact
state that used to crash (zero equipped items reaching a >1-max slot check;
Makhleb worship reaching `should_rest()`), and preserve existing behavior
everywhere else, since a Lua table result is untouched by either guard.

### Config flag, not a silent fix

Per PLAN.md §8/Phase 2 ("each ships behind a config flag and is validated
per the experiment protocol"), both guards are gated by one new rc-settable
global, `QW_BUGFIX_LUA_ERRORS` (`campaign.rc.tmpl`, threaded through
`ops/rc-gen.py`'s `write_run_dir(..., bugfix_lua_errors=True)`,
`ops/runner.py`'s `run_game(..., bugfix_lua_errors=True)`, and
`ops/campaign.py`'s `--disable-bugfix-lua-errors` CLI flag). Default/unset
behaves as `true` (fixed) — future campaigns get the fix automatically. Set
to `false`, both guards fall back to the original unguarded expression,
reproducing the exact original crashes — this is the experiment's control
arm, not a hypothetical: `ops/bugfix-lua-errors-test.py` proves both
directions live against the real pinned binary (see below), and
`data/experiments/lua-error-bugfix/` (see the follow-up experiment) uses it
to measure the fix's actual effect on the lua_error rate, rather than
asserting it must help.

## Verification

`ops/bugfix-lua-errors-test.py` drives crawl's own interactive Lua console
(wizard mode `&`, confirm, then Ctrl-U — `wizard.cc`'s
`debug_terp_dlua(clua)`, which evaluates code in the *same* clua
environment qw.lua runs in) against the real pinned+patched binary, and
calls `qw_hostile_servants_timer() + 100` and
`qw_equip_slot_or_empty(false, "ring")` directly:

- flag on (default): both return a value (`100`, `false`) with no error.
- flag off: both reproduce a crash of the same class as the original —
  `qw_hostile_servants_timer() + 100` → "attempt to perform arithmetic on
  ... a nil value" (the generic form, since Lua can't name an anonymous
  function-return value the way it names a direct global reference — same
  bug class as the original "global 'hostile_servants_timer'" message, not
  byte-identical text); `qw_equip_slot_or_empty(false, "ring")` → "attempt
  to index ... a boolean value" (byte-identical class to the original).

This intentionally does not go through real chargen/gameplay to reach these
states (e.g. actually joining Makhleb via wizard-mode religion-join, or
playing an unarmed Felid to the exact equipped-nothing moment): early
attempts at scripting the wizard-mode key sequence by hand hit real
choreography bugs (a second `&` keypress is itself a wizard sub-command,
`wizard_list_companions()`, not a way to reopen the command prompt — easy
to get wrong with blind timed sends, fixed by expecting each prompt's exact
text before sending the next key) and, per the non-reproducibility finding
above, gameplay-driven repro of the *original* bug is inherently flaky.
Calling the guard functions directly via the console exercises the real
global environment (the real unassigned global; the real rc-settable flag)
without that flakiness.

## Alternatives considered

- **Fixing `turn_memo`/`turn_memo_args` globally** (e.g. having every
  caller receive `nil` instead of `false`) would be a larger, riskier
  change — an unknown number of other call sites across qw's source may
  already depend on the `false` sentinel distinguishing "no result" from
  "not yet cached" in ways not audited here. Scoped, call-site guards are
  smaller and don't require auditing all of `turn_memo`'s other callers.
- **Assigning `hostile_servants_timer` a real, live value** (reviving
  whatever removed feature originally maintained it) is out of scope: this
  project runs a stock qw against a stock crawl and treats qw's own AI as a
  fixed baseline (per §5), not something to feature-extend. Guarding a dead
  global to stop it crashing is a bug fix; resurrecting a removed AI
  feature would be new behavior.

## Follow-up

A pre-declared Phase 2 experiment (`ops/experiment.py` scaffolding,
`data/experiments/lua-error-bugfix/`) measures the fix's actual effect on
the `lua_error` rate on held-out validation seeds against the frozen
phase1-500 baseline, per PLAN.md §8.

**Result:** 300 validation-split seeds/arm (`data/experiments/lua-error-bugfix/seeds.json`,
disjoint from phase1-500's `0..499`), `--turn-budget 20000 --wall-cap-secs
900`. Control (`bugfix_lua_errors=false`) sanity-checks against the frozen
baseline as expected: 17/300 = 5.67% `lua_error`, matching phase1-500's
5.2% within noise (predeclaration's hypothesized baseline). Treatment
(`bugfix_lua_errors=true`): 1/300 = 0.33%.

`ops/experiment.py`'s `evaluate_predeclaration`: rate difference −5.33 points
(95% CI −8.56 to −2.74), clears the predeclared 2-point minimum effect with
the CI excluding zero in the declared "decrease" direction —
`declared_improvement: true`. Full numbers in
`data/experiments/lua-error-bugfix/result.json`. **`QW_BUGFIX_LUA_ERRORS` is
confirmed effective; no code change needed since it already defaults to
fixed-on.**

### Addendum — Troll/Felid `lua_error` clusters in phase1-500 fully explained, no new bug

The Phase 1 exit review flagged Troll (46.2% bad rate) and Felid (36.8%) as
the next candidates worth checking against this fix's shape before assuming
they need new investigation. Checked directly: grepped every
`phase1-500-*` run whose `combo` starts `Tr`/`Fe` and status is `lua_error`
(9 runs total: 6 Felid, 3 Troll) against each run's own
`morgue/*.txt` crash text. All 9 land on exactly one of this decision's two
bugs — 5 at the combined-`qw.lua:3791` site (bug 1, `cur_equip` boolean
index — Felid's near-permanent zero-equipment state makes it the most
exposed species) and 4 at `qw.lua:14282` (bug 2, `hostile_servants_timer` —
Makhleb worship, unrelated to species; these happened to sample as
Troll/Felid characters who worshipped Makhleb, not a species-specific
mechanism). No third crash signature found. **No new Phase 2 item needed
for Troll/Felid specifically** — their elevated phase1-500 bad-rate is
this decision's two bugs, already fixed and already measured above.
