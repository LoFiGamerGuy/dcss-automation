# JOURNAL

Append-only working memory. **Newest entries at the bottom.** If you are a fresh
session, the last **Next step** below is where you begin.

Entry format:

```
## <ISO date> — <short title>
**Did:** ...
**Result:** what passed / what failed, with the actual error if it failed
**Next step:** the single most specific thing the next session should do
```

Write the *Next step* line **before** starting anything long or risky, not after.

---

## 2026-08-12 — Repo prepared for autonomous operation

**Did:** Set up the autonomous runtime. Created an isolated WSL2 distro
(`dcss-agent`, Ubuntu 24.04) with the Windows filesystem unmounted and interop
disabled. Installed the crawl build toolchain (gcc 13, make, ncursesw, lua5.1
headers, libsqlite3, zlib, bison, flex, python3-yaml) and Claude Code 2.1.228.
Cloned the repo to `~/work/dcss-automation` on ext4. Added `CLAUDE.md`,
`PROMPT.md`, `ORCHESTRATOR.md`, `ops/supervise.sh`, and `ops/config.env`.

**Result:** Runtime ready. No project code written yet — `PLAN.md` Phase 0 has
not been started.

**Next step:** Begin `PLAN.md` §9 Phase 0. First concrete task: decide and
record the vendoring mechanism (submodule vs. pinned shallow clone) in
`docs/decisions/002-vendoring-mechanism.md`, then check out `crawl/qw` at a
candidate commit pair — qw master, plus a crawl commit near the 0.32-a0
changelog reference per `PLAN.md` §3 — into the vendor location, and record both
SHAs in a lock file. Do **not** start the build before writing the lock file and
a journal entry saying you are starting it.

## 2026-08-12 — Vendoring decided and pinned; commit-pin candidate found

**Did:** Wrote `docs/decisions/002-vendoring-mechanism.md`: vendoring is
pinned shallow clones driven by `ops/vendor-lock.json` (not submodules —
`vendor/` is gitignored and disposable, matching the existing `.gitignore`
comment), qw patches are an overlay dir (`patches/qw/*.patch`, empty so far),
applied by `ops/fetch-vendor.sh`. For the commit pair (§3): confirmed network
egress works from the `dcss-agent` distro (github.com reachable). qw master's
`changelog.md` states verbatim "This version supports DCSS 0.32-a0" for its
top (0.4-a) entry. crawl's repo has an exact annotated tag `0.32-a0` whose
dereferenced commit is `a7cece931a0f6eb29acd71721463a2d2f9d4cde7`. Pinned:
crawl `a7cece93...` (tag 0.32-a0), qw `8698adcf...` (master tip
2026-08-12). Ran `ops/fetch-vendor.sh`: both shallow-fetched the exact pinned
SHA on the first try (GitHub allows shallow fetch of an arbitrary commit, not
just branch tips) into `vendor/crawl` and `vendor/qw`.

**Result:** Vendor fetch reproducible and fast (shallow, seconds). Have not
yet attempted a build — that's next and is the risky/long part.

**Next step:** Build crawl from `vendor/crawl` with `DGL_MILESTONES` defined
(PLAN.md §6 — stock local console builds do NOT write milestones without this;
it's normally gated behind the `DGAMELAUNCH` server block in `AppHdr.h`, so
this needs either a small patch to `AppHdr.h` or an equivalent build define).
Check crawl's `Makefile`/`INSTALL.md` under `vendor/crawl/crawl-ref/source`
for the exact define mechanism before patching blindly. If the build is going
to take more than a couple minutes, start it detached per `CLAUDE.md` (nohup +
log to `logs/`) rather than blocking the session on it. After a successful
build, verify `-list-combos` on the binary (Task #3) before going further —
that flag's existence/format is unverified for this exact commit.

## 2026-08-12 — DGL_MILESTONES is a clean build flag, not a source patch; build started

**Did:** Read `AppHdr.h`: `DGL_MILESTONES` (line ~200) sits inside the
`#ifdef DGAMELAUNCH` block, but is *independently* `#ifdef`-guarded at every
use site (`command.cc`, `hiscores.cc` — `mark_milestone()` itself only checks
`defined(USE_TILE_WEB) || defined(DGL_MILESTONES)`, no other DGAMELAUNCH
machinery required). Turning on the whole `DGAMELAUNCH` block would be worse
for unattended local play — it also pulls in `DGL_PAUSE_AFTER_ERROR` (blocks
on stdin "hit Enter" after any error — fatal for automation) and `WATCHDOG`.
So: no source patch. crawl's `Makefile` documents
`EXTERNAL_DEFINES="-DVERSIONED_CACHE_DIR"` as the sanctioned way to inject a
single define (`Makefile:81-82`, consumed at `DEFINES := $(EXTERNAL_DEFINES)`
line 157) — exactly PLAN.md §6 option 1's "small build-flag".

Also found: shallow `--depth 1` clones carry no tags, so `git describe`
(used by crawl's `Makefile` for `SRC_VERSION` and qw's `make-qw.sh` for its
embedded version string) fails and yields an empty string. Not fatal to the
Linux console build (the only consumer of `MAJOR_VERSION` is the Windows
packaging target) but would leave qw's `%VERSION%` substitution blank, which
is bad for the run manifest's version provenance. Fixed by having
`ops/fetch-vendor.sh` create a local annotated tag `pinned` on the checked-out
commit in each vendor repo right after fetch — `git describe` now returns
`pinned` for both. Re-ran `fetch-vendor.sh`, confirmed.

Started the build detached: `make EXTERNAL_DEFINES="-DDGL_MILESTONES" -j18`
in `vendor/crawl/crawl-ref/source`, PID 1957 (disowned), log at
`logs/crawl-build-1.log`. No TILES (console-only, matches PLAN §5 "console
build"). Chose `-j18` of 24 CPUs to leave headroom per `CLAUDE.md`.

**Result:** Build in progress at time of writing (compiling steadily,
several hundred `.cc` files expected — crawl is a large C++ codebase, likely
several-minutes wall time on 18 threads). Not yet confirmed to succeed.

**Next step:** Check `logs/crawl-build-1.log` (`tail`, or `ps -p 1957` to see
if it's still running / check exit). If it succeeded, the binary should be at
`vendor/crawl/crawl-ref/source/crawl`; run `./crawl -list-combos` and
`./crawl -version` to confirm the milestones feature banner ("Milestones" in
`_get_version_features()`, gated on the same `DGL_MILESTONES` define) and
combo listing both work (Task #3). If the build failed, read the actual
error in the log — do not re-guess blindly, the log will show the real
missing dependency or compile error. If it's still running when this session
ends, leave it running (it's detached/disowned) and say so explicitly in the
next journal entry rather than waiting on it silently.
