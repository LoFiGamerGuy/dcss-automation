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
