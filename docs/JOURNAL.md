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
