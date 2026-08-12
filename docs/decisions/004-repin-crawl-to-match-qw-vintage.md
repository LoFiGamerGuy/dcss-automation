# 004 — Re-pin crawl to qw's actual vintage, not the earliest 0.32-a0 commit

**Date:** 2026-08-12
**Status:** accepted

## Context

The GrBe canary (see `ops/run-canary.py`) reproducibly hit a Lua error a few
turns into a real game, after the first monster (a rat) came into view:

```
attempt to call field '?' (a nil value)
```

at `monster-class.lua`'s `Monster:can_use_doors()` →
`self:property_memo("can_use_doors")` → `self.minfo["can_use_doors"](...)`.
`grep`ing the pinned crawl's `l-moninf.cc` `moninf_lib[]` registration table
confirmed `can_use_doors` isn't registered — qw calls a crawl lua binding
that doesn't exist on our pin. Not a canary-harness bug; a genuine
vendor-pair incompatibility.

## Root cause

Traced with full (non-shallow) clones of both repos:

- qw added `Monster:can_use_doors()` in commit `667743d` (2024-06-08),
  requiring a matching crawl-side binding.
- crawl added that binding (`moninf_get_can_use_doors`) in commit
  `029dca9f2a` (2024-05-04).
- Our original crawl pin (`a7cece93`, tag `0.32-a0`, **2024-01-12**) predates
  both — by 4-5 months.
- qw's `master` branch, despite being fetched "at tip" on 2026-08-12, has not
  received a commit since **2024-07-15** (`8698adc`) — the branch is
  dormant, not actively current.

The original pin (docs/decisions/002) chose the *first* commit reachable from
tag `0.32-a0` on the theory that qw's changelog line "This version supports
DCSS 0.32-a0" pins to that tag. That's wrong: `0.32-a0` turns out to be a
long-lived `git describe` epoch — crawl's alpha cycle for 0.32 ran for
**1700+ commits** before the next tag (`0.32-b1`) was cut — so "supports
0.32-a0" describes a multi-month window, not a single commit. qw was
developed against crawl as it existed in that window *up to qw's own last
commit date*, not against the window's first instant.

## Choice

Re-pin crawl to `a504a9fe27e86e3ae0ab4abfa21f257b016f344d` (2024-07-15),
date-matched to qw's actual last commit rather than fetch time. Verified:
- `git describe` on this commit: `0.32-a0-1739-ga504a9fe27` — still inside
  the same tag epoch as before, so `describe_tag: "0.32-a0"` in
  `ops/vendor-lock.json` is unchanged and still correct.
- `029dca9f2a` (the `can_use_doors` binding) is an ancestor — confirmed via
  `git merge-base --is-ancestor`.
- `patches/crawl/0001-weapon-json-clo.patch` (docs/decisions/003) still
  applies cleanly with no offset — the ~6-month gap didn't touch
  `newgame.cc`/`playable.cc`/`initfile.cc` in ways that conflict.

Rejected alternatives:
- **Pin crawl to its current master tip (0.35-a0, 2026-08-10).** Considered
  briefly since qw was fetched "at tip" the same day. Rejected once qw's
  actual last-commit date (2024-07-15) surfaced: crawl's API has moved
  through three more dev cycles (0.33, 0.34, 0.35) since then, which would
  very likely introduce *more* incompatibilities in the other direction
  (qw calling bindings crawl has since renamed/removed), not fewer. Vintage
  match, not recency, is what avoids drift here.
- **Patch qw to avoid `can_use_doors`.** Rejected — the missing piece is
  crawl-side plumbing already implemented upstream by the same devteam that
  maintains qw; re-deriving it in a qw patch risks silently-wrong pathing
  logic (the exact failure mode flagged in decision 003), for no benefit
  over just picking a crawl commit that already has it correctly.

## Consequences

- `ops/vendor-lock.json`'s `crawl.commit` changed; `ops/fetch-vendor.sh`,
  rebuild, and manifest regeneration must be re-run (not just re-diffed)
  after this decision.
- The legal-character manifest counts may shift slightly (species/job
  additions between January and July 2024, e.g. qw's changelog mentions
  "Support for Coglins and dual wielding" as a *qw*-side change reacting to
  a *crawl*-side species addition in this window) — expected, not a bug;
  re-verify against the new binary's own `-playable-json`/`-weapon-json`
  output rather than the counts recorded in decision 003.
- General lesson for future re-pins (Phase 2 and beyond): when one side of
  a vendor pair is "pinned to a tag" and the other is "pinned to a branch
  tip," match them by the **branch-tip side's actual last-commit date**, not
  by fetch date or by the tag's literal first commit. Record both repos'
  commit dates in the lock file note, not just SHAs, so this is checkable at
  a glance next time.
