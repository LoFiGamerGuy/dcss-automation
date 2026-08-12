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

## 2026-08-12 — Manifest + canary suite green after fixing 3 real bugs (build, harness, vendor pin)

**Did:** Picked up mid-flight: a prior invocation had built crawl successfully
(build-2), discovered `-list-combos` doesn't exist on the pin and added
`-playable-json`/`-weapon-json` CLOs instead (`docs/decisions/003`,
`patches/crawl/0001-weapon-json-clo.patch`), fixed the `git describe`
"Version string 'pinned' is malformed" build failure (per-repo `describe_tag`
in `vendor-lock.json`), and wrote `ops/generate-manifest.sh` +
`ops/run-canary.py` + `ops/canary/canary.rc.tmpl` — but left it all
uncommitted and unjournaled (a real gap: two full sessions of work were at
risk of being lost). Verified all of it, found and fixed three more bugs
along the way, then committed the whole thing as one coherent unit.

Bugs found and fixed this session:
1. **qw.lua never generated.** `ops/fetch-vendor.sh` fetches qw's raw
   `source/*.lua` files but qw.rc only loads bot logic if they're combined
   into `qw.lua` first (`make-qw.sh`, README "Method 1") — not checked into
   qw's repo, and not run by our fetch script. Fixed: `fetch-vendor.sh` now
   runs `make-qw.sh` after every fetch. Without this qw never actually plays
   — the rc loads with no bot logic and just sits at the welcome screen.
2. **`canary.rc.tmpl` never included qw.lua either**, and separately, the
   game's opening `--more--` prompt blocks all input (including clua hooks)
   until dismissed — qw's own reference automation (`util/qw.exp`) sends
   `\r\t` for exactly this reason (`\r` dismiss, `\t` toggle start). Our
   template sets `AUTO_START = true` already, so `run-canary.py` now sends
   only `\r` after the "Welcome," banner (sending Tab too would toggle qw
   back *off*). Both bugs together meant every canary produced zero bot
   activity and the harness misread that as company for bug #3.
3. **`run-canary.py`'s inactivity-timeout branch classified as "hang"
   without checking for a Lua error first.** A crashed-and-frozen game looks
   identical to a genuinely stuck one from the outside (both stop producing
   output) — the deadline-end path checked `ERROR_PATTERNS` but the
   15-second-inactivity path returned early. Factored both into a shared
   `_classify()`. This is what surfaced bug #4 below instead of hiding it as
   a generic hang.
4. **Real vendor incompatibility, not a harness bug:** GrBe reproducibly hit
   `attempt to call field '?' (a nil value)` a few turns in, from
   `Monster:can_use_doors()` calling a crawl lua binding
   (`moninf_get_can_use_doors`) that our pinned crawl commit doesn't have.
   Root-caused with full (non-shallow) clones of both repos: qw added
   `can_use_doors` 2024-06-08; crawl added the matching binding 2024-05-04;
   our original pin (`a7cece93`, tag `0.32-a0`) was **2024-01-12** — 4-5
   months too early. The deeper finding: `0.32-a0` is a long-lived
   `git describe` epoch (1700+ commits before the next tag `0.32-b1`), so
   "qw's changelog says it supports 0.32-a0" does not mean "pin the first
   commit of that tag" — it means "pin a commit contemporaneous with qw's
   own development window." qw's `master` branch, despite being fetched
   "at tip" today, hasn't been touched since **2024-07-15**. Re-pinned crawl
   to `a504a9fe27e86e3ae0ab4abfa21f257b016f344d` (2024-07-15, date-matched
   to qw, not fetch-date-matched) — full reasoning and rejected alternatives
   in `docs/decisions/004-repin-crawl-to-match-qw-vintage.md`.

After all four fixes: rebuilt clean from the corrected lock file (reproducible
build re-verified), regenerated the manifest (35 species incl. Coglin — added
between the old and new pin — 25 jobs, 665 combos, 238 weapon-choice combos),
and ran all 8 required canaries (GrBe, HuCK zealot, HuCj caster, FeSu Felid,
MuNe Mummy, GnWn Gnoll, DgFE Demigod, FoAl Formicid) at seed 1 / 45s budget —
all `ok`, confirmed by manually inspecting raw output (real movement, combat,
in GrBe's case a full death) and cross-checked with a manual grep for error
patterns.

**Result:** Phase 0 exit criteria status: reproducible build ✓ (re-verified
via this session's from-scratch rebuild after the re-pin); canary suite ✓ (8/8
ok); sampler-support-set-diff-empty ✓ by construction (manifest generated
directly from the running binary's own CLOs, nothing hand-maintained to drift).
**Not yet done:** the telemetry acceptance test (PLAN §6 — DGL_MILESTONES file
must appear with *exact* expected event records for a scripted game covering
branch entry/rune/death, not just "a file appeared"); the ~50-game
wall-clock/CPU/memory throughput measurement that feeds Phase 1 sizing.
Committed as one commit (build script fix, vendor re-pin, decisions 003+004,
manifest, canary infra).

**Next step:** Write the telemetry acceptance test next — script a short game
via wizard-mode/lua console commands (or a scripted rc) that forces a branch
entry, a rune pickup, and a death in as few turns as possible, run it against
the current pinned+rebuilt binary (`DGL_MILESTONES` already compiled in —
confirmed via `-version` feature banner previously, worth re-confirming since
the binary was rebuilt from a different commit), and assert the milestones
xlog file contains exactly the expected event records/fields — not just that
the file exists. After that, do the ~50-game throughput measurement: start it
**detached** (nohup + `logs/`, PID recorded here first) since even at ~45s
budget/game that's ~40 min serial — parallelize across a handful of workers
(leave CPU headroom per CLAUDE.md) rather than running serially, and do not
idle-wait on it; go do the telemetry test work while it runs if sequencing
allows, or leave it running across session boundary and say so explicitly.

## 2026-08-12 — Telemetry acceptance test built; found & documented a real PLAN.md correction; throughput campaign running

**Did:** Wizard-mode is a dead end for scripting milestone events —
`mark_milestone()` suppresses everything except `type="crash"` whenever
`you.wizard`/`you.explore` is set (`hiscores.cc` ~line 3146), so any
approach using `&`/debug commands to force a branch/rune/death would test
nothing. Instead drove real (non-wizard) qw games via the same pexpect
approach as `run-canary.py` and searched for a seed+combo that naturally
hits interesting events fast. `GrBe` seed 1 reliably dies around D:7
(reproduced identically twice, including once waiting for natural process
EOF instead of force-killing, to rule out a race); `MiBe` seed 2 reliably
picks up a Sewer portal within ~120s (`br.enter`/`br.exit`).

**Real finding, not a harness bug:** that `GrBe` death (confirmed via the
final logfile row: `killer=Maurice`, `hp=-1`) never produces a milestone
record. Read `ouch.cc`: `mark_milestone("death", ...)` is gated on
`you.lives != 0`, which is an extra-lives game-mode mechanic, not standard
permadeath — so for a normal game, death is structurally never a milestone
event, only a final-logfile-row event. This directly refines `PLAN.md` §6's
death-telemetry assumption; full writeup in
`docs/decisions/005-telemetry-verification-and-death-milestone-correction.md`.
Rune pickup wasn't reached in any 120s-budget scripted attempt (needs real
depth — a Lair-branch end or deeper) so it's unverified as of this entry;
see the running campaign below.

Built `ops/telemetry-test.py`: runs the fixed `MiBe`/seed-2/120s repro,
parses the milestones xlog with a correct `::`-escape-aware field parser
(matched against `hiscores.cc`'s actual `_xlog_split_fields`/`_xlog_unescape`
algorithm, not a naive `:`.split()), and asserts exact fields on `begin`
(1 record, exact text), `uniq` (≥1, `place`/`br` present), and `br.enter`
(1, `oplace` present and distinct from `br`). Ran it twice back-to-back —
byte-for-byte identical milestone sequence both times, confirming this pin
is fully deterministic. **Passes.**

Also built `ops/throughput-probe.py` for the PLAN §9 exit criterion
("measure per-game wall-clock/CPU/memory over ~50 mixed games... throughput
report exists and feeds Phase 1 sizing") — samples combos from the
committed manifest, runs each under `/usr/bin/time -v` (via `script -qefc`
for a pty; note `time -v`'s report only reliably lands in the `script`
typescript file, *not* in the subprocess's own captured stderr — that took
a smoke-test round to discover) with a 900s safety cap (not a turn budget —
Phase 1's real runner does turn budgets; this is deliberately just measuring
wall-clock, so wall-clock is the cap), and writes percentile wall/CPU/RSS to
a JSON report. Smoke-tested at n=2 before trusting it with the real run.
This run also doubles as another rune-milestone attempt, now with a 900s cap
instead of 120s, across 50 varied combos instead of 4.

**Started detached, not yet collected:** `python3 ops/throughput-probe.py
--n-games 50 --safety-cap-secs 900 --workers 8 --out
data/throughput-report.json`, PID **21247** (disowned), log at
`logs/throughput-probe-1.log`, started 2026-08-12 08:20 EDT. 8 parallel
workers on 24 CPUs (leaves headroom per CLAUDE.md). Worst case ~50/8 × 900s
≈ 94 min if every game hits the safety cap; expect much less in practice
since qw deaths are usually faster than that. Report lands at
`data/throughput-report.json` when done.

Committed telemetry test + decision 005 + throughput probe script in this
entry's commit (the throughput *report* itself isn't committed yet — it
doesn't exist until the detached run finishes).

Also noted: a separate/parallel invocation pushed unrelated "local-model
overnight profile" commits (`e7a720f`..`587f7b3`) to `origin/main` while this
session was in progress — no file overlap, rebased cleanly. Worth knowing
concurrent pushes to `main` are actually happening, not just a hypothetical
the guardrails were written for.

**Result:** Phase 0 exit criteria status update — reproducible build ✓,
canary suite ✓ (8/8), sampler-support-set-diff-empty ✓, telemetry test ✓
for `begin`/`uniq`/`br.enter` (exact fields asserted, deterministic re-run
confirmed) with `death` correctly *not* asserted (§6 assumption corrected,
see decision 005). **Still open:** rune milestone unverified (campaign
above may catch it as a side effect, un-guaranteed); throughput report not
yet collected (campaign in flight).

**Next step:** Check `ps -p 21247` and `tail logs/throughput-probe-1.log` —
if the process exited, read `data/throughput-report.json`: report
`wall_secs`/`max_rss_mb` median+p95 (this is the number Phase 1 fleet sizing
needs), check `rune_milestone_count` (if >0, grab one full milestones file
from that run's log/output before it's lost and fold an exact-field rune
assertion into `ops/telemetry-test.py`/decision 005 — if still 0 after 50
games at 900s, that itself is worth recording as "rune verification deferred
to Phase 1 campaign data, not a Phase 0 blocker" rather than chased further
synchronously). Commit `data/throughput-report.json` once collected. If the
process is still running, leave it (detached) and say so in the next entry
rather than waiting on it. Once throughput + (best-effort) rune status are
recorded, Phase 0's only remaining open item is rune-exact-field
verification if never caught — decide then whether to accept the fallback
(logfile-only) framing for rune too, or spend one more longer probe on it,
and move on to Phase 1 (sampler + rc generation + runner state machine).

## 2026-08-12 — Phase 1 sampler built and tested while throughput campaign ran

**Did:** Picked up with the throughput probe (PID 21247) still running from the
prior entry — checked it first (`ps -p 21247`, `logs/throughput-probe-1.log`):
still alive, all 8 worker slots occupied by in-flight games (checked via
`/tmp/dcss-throughput-*` dirs, which are only removed on a game's completion —
zero had completed yet at the ~6.5 min mark). Games here run to natural
completion under a 900s cap rather than a canary's ~45s budget, so a multi-
minute wait before the first result is expected, not a stall; log output is
also just sitting in Python's block-buffered stdout (redirected to a file,
not a tty) until the process exits, so an empty-looking log tail is
consistent with normal progress, not evidence of one. Left it running
(untouched, still detached) and did not wait on it — moved on to Phase 1 work
that doesn't depend on its output.

Built `ops/combos.py`: the §2 `uniform-pairs` sampler. Given the archived
manifest and a *dedicated character-RNG seed* (deliberately never the game
seed, per §2 step 2), it samples one (species,background) pair uniformly,
then — if that combo has a starting-weapon choice — a weapon uniformly over
its legal options, and emits the exact rc `combo=` string (confirmed the
`SpJo.weapon name` dot-syntax by reading `newgame.cc`'s `_choose_char`, which
`split_string(".", combo)` — not documented anywhere, had to read the parser).

Built `ops/sampler-test.py`, the Phase 1 exit-criterion test, with three
checks: (1) support-set diff — re-queries the *live* pinned binary's
`-playable-json`/`-weapon-json` right now and diffs against the committed
manifest, so this doesn't just trust the manifest was correct at generation
time; (2) determinism — same (manifest, char_seed) always samples the same
character; (3) goodness-of-fit — stdlib-only chi-square tests (no
scipy/numpy in this environment, so implemented Acklam's normal-quantile
approximation + Wilson-Hilferty chi-square-quantile approximation from
scratch) for both pair-selection uniformity (single test, df=664) and, per
weapon-choice combo with enough samples, weapon-selection uniformity
(Bonferroni-corrected across the ~230 testable combos so many independent
per-combo tests don't inflate the false-positive rate). Hit and fixed one
real bug while building this: 8 combos (all Felid) have exactly one "choice"
(`unarmed` only) in the weapon manifest — not a real distribution, chi-square
df=0 crashed; excluded len==1 combos from the testable set. Sanity-checked
the test's actual detection power by deliberately biasing pair selection
5:1 favoring one combo and confirming the chi2 stat blew past critical
(531726 vs. crit 782) — not just that it passes on good input, which alone
wouldn't distinguish a real test from a no-op. `PASS`es at n=200k in ~6s.

Committed both files (`cc0e436`) and pushed.

**Result:** Phase 1's sampler sub-deliverable (§9 Phase 1 "sampler...") is
done and self-tested — goodness-of-fit exit criterion for the sampler
specifically now passes as an automated, re-runnable test, ahead of the rest
of Phase 1 (rc generation, runner state machine, collector) which is not
started. Phase 0 is still not closed: throughput report not yet collected
(campaign still running, see below), rune milestone still unverified.

Checked the probe again before ending this entry: still running
(`ps -p 21247` alive, ~elapsed continuing to climb), still no completions in
`/tmp` teardown yet. **Leaving it running across this session boundary.**

**Next step:** Same as the unresolved half of the prior entry — check
`ps -p 21247` / `logs/throughput-probe-1.log` / `data/throughput-report.json`
first thing next session. If done: pull `wall_secs`/`max_rss_mb`
median+p95 for Phase 1 fleet sizing, check `rune_milestone_count`, commit the
report. If still running (plausible — worst case ~94 min from its 08:20
start, and this session ended before that), leave it and keep checking at
the start of future sessions rather than blocking on it. Either way, Phase 1
work can continue in parallel: next concrete piece is `ops/rc-gen.py` (or
extend `combos.py`) to produce a full per-run rc file (generalizing
`ops/canary/canary.rc.tmpl`'s pattern — this file forces `AUTO_START`/
`DELAYED` for canaries; the real per-run template needs qw's `QUIT_TURNS`
and `c_persist`-clearing per §7 baked in, not just a forced combo), then the
runner state machine (§6: write-ahead manifest, the 10 terminal statuses,
progress-based hang detection) — note turn-budget *sizing* specifically
should wait for the throughput numbers, but the state machine's structure
does not depend on them.
