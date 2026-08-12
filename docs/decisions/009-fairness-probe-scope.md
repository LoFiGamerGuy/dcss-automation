# 009 — Fairness probe test: live-tested monster visibility, source-only for items

**Context.** PLAN.md §7 says "Phase 1 includes probe tests: assert that
unseen monsters and unidentified item identities are absent from everything
the policy layer can read." This isn't one of §9 Phase 1's gating exit
criteria (those are goodness-of-fit, forced-failure drills,
parallel-isolation, the reconciliation invariant, and byte-identical
reports), but §7 calls it out as in-scope work, so `ops/fairness-probe-test.py`
was built to cover the monster-visibility half live.

**Monster visibility — live-tested.** `l-moninf.cc:mi_get_monster_at`
(everything a policy's `monster.get_monster_at(dx, dy)` calls resolve to)
turned out to have a *stronger* guarantee than PLAN's §4.1 description
implied: the `COORDSHOW` macro (`cluautil.h`) rejects any coordinate beyond
`ENV_SHOW_OFFSET` (= `LOS_MAX_RANGE` = `LOS_RADIUS` = 8 in the pinned
source, `defines.h`) with a hard Lua error, before the `you.see_cell(p)`
visibility check is even reached — there's no queryable coordinate outside
LOS at all, not just a nil for one. `fairness-probe-test.py` confirms this
live (a query one cell past the radius errors) plus a positive control
(real qw-driven play does see non-nil results within LOS at least once, so
the bounds check isn't vacuously passing because the mechanism never works
at all). See the test's own docstring for a real bug hit and fixed while
building it (`crawl.mpr()` silently dropped a message under this test's
exact two-messages-per-tick structure; `crawl.stderr()` fixed it — a pty
capture/message-pane detail, not a fairness-relevant finding on its own,
but worth knowing for any future probe script in this vein).

**Item identification — source-verified only, not live-probed.** `l-item.cc`
confirms the analogous claim by inspection: `fully_identified` is an
explicit boolean field, and identity-gated fields like `ego`/`artefact_name`
/`artprops` are conditioned on `item_ident(*item, ISFLAG_...)` checks before
they expose anything (e.g. `l-item.cc:861-862` gates `artprops` on
`item_ident(*item, ISFLAG_KNOW_PROPERTIES)`). This wasn't extended into a
live probe in this pass: unlike monster visibility (any level has monsters
outside LOS essentially by default), constructing a *guaranteed*-unidentified
item scenario needs a specific background's starting kit or a controlled
pickup, which is meaningfully more scenario-engineering for something that
isn't a gating criterion.

**Decision.** Ship the monster-visibility live probe now; leave item
identification as source-verified (documented here, not asserted by a
running test). If a future session wants to close this gap, the concrete
path is: pick a background from the legal-character manifest that starts
with a non-artefact identifiable item (a potion or scroll background, most
easily), read its identity state via `items.inventory()[i].fully_identified`
before quaffing/reading it, and assert it's `false` pre-identification and
that ego/artefact fields are absent — mirroring this test's structure
(pcall-wrapped probes over `crawl.stderr()`, not `crawl.mpr()`, per the note
above).
