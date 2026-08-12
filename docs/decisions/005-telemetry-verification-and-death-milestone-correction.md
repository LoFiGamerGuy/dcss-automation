# 005 — Telemetry verified; PLAN's "death is a milestone" assumption corrected

**Date:** 2026-08-12
**Status:** accepted

## Context

`PLAN.md` §6/§9 requires Phase 0 to verify the `DGL_MILESTONES` xlog file
"appears and asserts exact expected event records and fields for a scripted
game — branch entry, rune, death." `ops/telemetry-test.py` implements this
for `begin`, `uniq`, and `br.enter`/`br.exit`, all confirmed against the
pinned+rebuilt binary (commit `a504a9fe`, see decision 004) with exact xlog
field checks (parsing the real `::`-escaping scheme from `hiscores.cc`'s
`_xlog_split_fields`/`_xlog_unescape`, not a naive `:` split).

## Finding: standard permadeath does not write a milestone record

Ran the same scripted game (combo `GrBe`, seed 1) to an actual character
death twice, independently, once killing the process on 15s inactivity and
once waiting for natural process exit and dismissing all post-death prompts
first (to rule out the harness racing the write). Both times: the death
(confirmed happened — `killer=Maurice`, `ktyp=mon`, `hp=-1` in the final
*logfile* row) produced **no corresponding `milestones` record**.

Root cause, found by reading `ouch.cc` (`ouch()`, ~line 1259):

```cpp
if (you.lives && !non_death)
{
    mark_milestone("death", lowercase_first(se.long_kill_message()).c_str());
    ...
}
```

`mark_milestone("death", ...)` only fires when `you.lives` is nonzero — i.e.
game modes with extra lives (not present in a standard game, where
`you.lives == 0` throughout). For an ordinary permadeath run, this branch
never executes. The death is instead captured only in the final row of the
*logfile* (not `milestones`) — which we'd already confirmed reliable
(`ktyp`, `killer`, `dam`, `sc`, etc. all present) via the canary suite in
`docs/decisions/003`/the 2026-08-12 journal entry.

This matches — and actually resolves — `PLAN.md` §6's own fallback framing
("the final logfile row … plus the morgue's turn-stamped notes") which was
written as a *hypothetical* fallback in case milestones didn't pan out. For
death specifically, it isn't a fallback — it's the only source. Branch entry
and rune pickup remain genuine milestone-file events, unaffected by this.

## Choice

- `ops/telemetry-test.py` asserts `begin`, `uniq`, `br.enter`/`br.exit`
  exactly, and explicitly does *not* assert a `death` milestone, with a
  comment pointing here so this isn't "rediscovered" as a bug later.
- Any future death/outcome telemetry (Phase 1's outcome-vector report, PLAN
  §1) must read the run's final logfile row, never the milestones file, for
  the terminal-status fields.
- Rune pickup (`type=rune`) is *not yet* verified — it wasn't reached within
  a 120s scripted budget at any seed tried (`GrBe`/`MiBe`, seeds 1-4).
  Getting a rune requires real depth (a Lair-branch end or deeper) which is
  plausibly tens of minutes of real bot play, not something to force
  synchronously in an interactive session. Left as an open item — see
  journal "Next step" for the plan to get this from a longer, detached probe
  rather than blocking Phase 0 sign-off on it further today.

## Validation

`ops/telemetry-test.py` (combo `MiBe`, seed 2, 120s budget) is a **fixed,
reproducible repro** — re-run twice back to back in this session, byte-for-
byte identical milestone sequence both times (deterministic given the pinned
crawl/qw commits and fixed seed). Confirms:
- `begin`: exactly 1 record, exact expected text.
- `uniq`: ≥1 record (9 in this repro), each with `place`/`br` fields and a
  `milestone` string starting `"killed "`.
- `br.enter`: 1 record (Sewer portal), with `oplace=D::6` (origin level) and
  `br=Sewer` (destination branch) correctly distinct — confirms the escaped
  `place=D::6` — the `PLAN.md`-style event linking a branch entry back to
  where it was entered from — decodes correctly through the `::`-unescape.
