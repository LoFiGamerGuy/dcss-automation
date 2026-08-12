# 002 — Vendoring mechanism: pinned shallow clones, not submodules; overlay patches

**Date:** 2026-08-12
**Status:** accepted

## Context

`PLAN.md` §3/§5 requires exact-commit pins of `crawl` and `qw`, reproducible on
a clean machine, with every run manifest recording both hashes. Two decisions
were left open: submodule vs. pinned shallow clone, and overlay-patch vs. fork
for our qw modifications.

`.gitignore` (written during runtime setup, before this note) already excludes
`vendor/` with the comment "pinned by lock file, never committed" — so the
shallow-clone direction was effectively pre-selected. This note makes it
explicit and adds the reasoning.

## Choices

**1. Vendoring: pinned shallow clones fetched by script from a lock file, not
git submodules.**

A submodule records a gitlink + `.gitmodules` and is *tracked by* the parent
repo, not excludable via `.gitignore`. That fights the "reproducible build
from lock info on a clean machine" acceptance test in two ways: submodule
history bloats `git clone` of this repo forever (crawl's history is large),
and a submodule pin lives in a git object most tooling treats as
infrastructure rather than as a versioned harness input alongside our own
config/patch hashes.

Instead: `ops/vendor-lock.json` is the single source of truth for
`{repo, commit}` for crawl and qw, committed to `main`. `ops/fetch-vendor.sh`
reads it and produces `vendor/crawl` and `vendor/qw` via `git init` +
`git fetch --depth 1 <repo> <commit>` + `git checkout FETCH_HEAD` (falls back
to a full clone + checkout if the remote rejects a shallow fetch of a
non-tip commit — GitHub's server does allow shallow-fetching arbitrary SHAs,
but this is not guaranteed for all future hosts). The lock file, not
`vendor/`, is what "pinned" means; `vendor/` is disposable build input,
exactly like a `node_modules` restored from a lockfile.

**2. qw patches: overlay directory (`patches/qw/*.patch`), not a fork.**

A fork (our own branch/commits on top of pinned qw) would need continuous
rebasing to stay diffable against upstream and complicates the "vendor/ is
disposable" property above — a fork is a stateful clone, not a reproducible
fetch. An overlay is a numbered set of unified diffs, committed in the main
repo (not gitignored), applied by `fetch-vendor.sh` in order after checkout,
recorded (patch set hash) in the run manifest per §5 point 5. Each patch is
small and self-explaining via its diff; if patches accumulate to the point a
fork would be clearer, that is a future versioned decision, not a default.

No patches exist yet (Phase 0 has not modified qw). The directory is created
empty with a `.gitkeep` placeholder.

## Reasoning

Both choices optimize for the same acceptance test: a fresh checkout of this
repo plus one script invocation must reproduce byte-identical vendor sources
from committed, diffable inputs (lock file + patches), with no large binary
history riding along in `main`.

## Consequences

- Anyone (including a fresh agent session) reproduces vendor sources with
  `./ops/fetch-vendor.sh`.
- Bumping either pin is a one-line edit to `ops/vendor-lock.json` plus a fresh
  canary pass (§3), not a submodule-update dance.
- If a patch needs amending, edit the `.patch` file directly; `fetch-vendor.sh`
  re-applies from a clean checkout every time, so patches never drift from
  what's actually running.
