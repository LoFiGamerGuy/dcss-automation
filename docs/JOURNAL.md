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
the start of future sessions rather than blocking on it.

## 2026-08-12 — rc generation built (sampler → rc → crawl handoff); throughput campaign still running

**Did:** Continued straight on from the prior entry rather than waiting idle
on the throughput probe (still running, checked again: `ps -p 21247` alive,
25+ min elapsed, `/tmp/dcss-throughput-*` churn shows ~8+ of 50 games already
completed and torn down, 8 still in flight — consistent with the plan, not a
stall).

Read `newgame.cc`'s `_choose_char` to confirm the (undocumented) rc `combo=`
weapon syntax: `"SpJo.weapon name"`, split on `.` — needed this to generate
weapon-choice combos correctly, not just guess at it.

Built `ops/campaign.rc.tmpl` (a generalization of `ops/canary/canary.rc.tmpl`
for real runs — `AUTO_START=true`/`DELAYED=false`, forced `combo=`) and
`ops/rc-gen.py`: combines `ops/combos.py`'s sampler output with the template
to produce (a) the write-ahead manifest row §6 requires before launch (run
ID, character, seeds, crawl commit, rc template hash) and (b) the materialized
rc file + save/morgue directory layout a launch needs. Confirmed `c_persist`
(§7 cross-game memory) needs no explicit clearing code: crawl's clua persist
API keys it to the save under `-dir`/`-name`, and every run already gets a
fresh unique pair of both — documented this reasoning inline rather than
adding dead code to "clear" something that can't be populated yet.

Built `ops/rc-gen-test.py`, an integration smoke test: samples 5 characters
(seeds 0-4, chosen because they already cover both a weapon-choice combo,
`FeFi.unarmed`, and a plain combo, `OnEE`, without needing to hunt for more),
materializes each via `rc-gen.py`, and confirms the pinned binary actually
accepts the generated rc and reaches the "Welcome," chargen banner — proving
the sampler → rc-gen → crawl handoff works end to end, not just that the
Python code runs. Hit real timing flakiness while building it: with the
throughput campaign's 8 concurrent crawl+lua processes competing for
CPU/disk, even a 40s expect-timeout produced one spurious failure
(`SpCA.falchion`); hand-verified via a manual `script`-wrapped run under the
same load that the game had in fact reached "Welcome," and full chargen
(`dbgSpCA the Spriggan Cinder Acolyte`, `-1 falchion (flame)` equipped) — it
was just slower than the timeout, not broken. Bumped the test's timeout to
60s and documented why in a comment (this is a real, load-dependent
timing fact worth remembering, not a one-off fluke to shrug off — if a
future runner's hang-detection thresholds are tuned only under idle-machine
conditions they'll misfire under real campaign concurrency). Reran clean:
5/5 pass.

Committed both pieces (`429a15c` → rebased to `9e60ad1` after a push
rejection from a concurrent session's unrelated systemd-supervisor commit,
`9efea34` — no file overlap, clean rebase, matches the recovery pattern
`docs/decisions` already established for this).

**Result:** Phase 1 now has two tested, independent building blocks done:
the §2 sampler (`combos.py`) and the launch-artifact generation
(`rc-gen.py`) that turns a sampled character into something crawl will
actually run. Both proven against the real pinned binary, not just unit
logic. Still not started: the runner state machine itself (§6 terminal-
status classification off real process/output signals, write-ahead
accounting persistence, progress-based hang detection), the collector, and
the outcome-vector report. Phase 0 still open on the same two items as
before: throughput report, rune-milestone verification.

Checked the probe once more before ending this entry: still running,
unchanged status. **Leaving it running across this session boundary again.**

**Next step:** First: collect the throughput probe result (`ps -p 21247`,
`data/throughput-report.json`) — same instructions as the last two entries,
not repeating them a third time, just: do this first. Then Phase 1's next
piece is the runner state machine proper: a `runner.py` that takes a
manifest row from `rc-gen.py`, launches crawl (reusing the CLO-building
pattern `rc-gen.py`'s `write_run_dir` already returns), and classifies the
outcome into exactly one of the §6 terminal statuses (`won | died |
quit_intentional | quit_stuck | lua_error | crashed | timeout_turns |
timeout_wall | invalid_telemetry | harness_failure`) using turn-count
instrumentation (not just wall-clock, which `run-canary.py`/
`throughput-probe.py` use as a stand-in — real turn-budget tracking needs
reading `you.turns`/similar from clua or the logfile, not built yet) plus
progress-based hang detection (no save/logfile/message mtime change for N
minutes — the specific N is a throughput-report-informed choice, still
pending). Forced-failure drills (induced Lua error, `kill -9`, hang) are
Phase 1's exit criterion for this piece and should be written alongside it,
the same way `sampler-test.py`/`rc-gen-test.py` were written alongside their
subjects this session — don't build the classifier and defer testing it.

## 2026-08-12 — Runner state machine built and drilled; throughput campaign still running

**Did:** Picked up with the throughput probe (PID 21247) still running —
checked it repeatedly across this session (13, 30, 42, 47 min marks), always
alive with workers actively cycling through combos (`/tmp/dcss-throughput-*`
churn, no stall signs). Left it running the whole session; still no report
at time of writing.

Before writing the classifier, dispatched a research agent to read the
pinned crawl source (not guess) for exactly how a game's end is recorded.
Key findings, all file:line-cited in `docs/decisions/006`: crawl's
end-of-game xlog row ("logfile", separate from the DGL_MILESTONES
"milestones" file) lands at `<-dir>/saves/logfile-seeded` (extra nested
`saves/`, `-seeded` qualifier from `-seed`), written synchronously
(fopen/write/fclose) the instant the game ends, before any post-game UI —
so polling for its appearance is race-free and doesn't need the process to
reach EOF. Its `ktyp=` field is authoritative: `winning`→won,
`quitting`→qw's own Ctrl-Q stuck-quit (`QUIT_TURNS`, the *only*
self-initiated quit path qw's `determine_goal()` has), `leaving`→qw's
"Escape" goal walking out D:1 without the Orb (a genuinely different,
deliberate exit), anything else→died (no single generic "died" value, it's
whichever real cause fired). No row is written at all if the process is
killed before reaching `ouch()`'s terminal branch — confirmed via the call
chain, not assumed.

Built `ops/xlog.py`: factored the milestones-file field parser out of
`telemetry-test.py` (unchanged behavior, re-verified: still PASSes) so
`runner.py` can reuse the same escape-aware parsing for the logfile row
instead of duplicating it.

Extended `campaign.rc.tmpl`/`rc-gen.py` with a harness turn-budget hook
(`TURN_BUDGET` Lua global, wraps qw's own `ready()`) for PLAN §6's
`timeout_turns`. First version also tried sending the Ctrl-Q "yes" quit
sequence from inside that same Lua hook — **hung**, reproduced twice by
hand: those keys queue into the same in-process macro buffer qw's own
`ready()` concurrently feeds every tick, and the two interleaved
unpredictably (once the process just sat alive forever after the sentinel
fired; once it produced an unrelated qw Lua error later in the run instead
of quitting). Fixed by having the Lua hook *only* print an on-screen
sentinel (`HARNESS_TIMEOUT_TURNS`) and moving the actual kill to
`runner.py`, watching the pty stream from outside — the same external
channel a human or `util/qw.exp` types into, so it can't race qw's
internal queueing. Verified: `--turn-budget 5` reliably classifies
`timeout_turns` in ~2s.

Built `ops/runner.py`: write-ahead `manifest.json` (written before spawn,
into the run's own directory — no shared-file locking needed since every
run already gets a unique dir) → materialize rc via `rc-gen.py` → spawn →
supervise (poll for the logfile row; watch for the timeout sentinel; the
established run-canary.py fix of checking error patterns before concluding
hang, now also applied before concluding wall-cap) → classify →
`result.json`. Library split into `monitor_game()` (spawn+supervise only)
and `run_game()` (adds the write-ahead/rc-gen/result.json wrapper), so
drills can inject failures into a hand-modified rc via `monitor_game()`
directly.

Built `ops/runner-drills-test.py` (Phase 1 exit criterion): all three named
drills against the real pinned binary, not a mocked classifier.
- **lua_error**: hand-broken `ready()` that always errors — clua catches it
  internally (non-fatal to the process), correctly caught by the
  error-pattern-before-hang check rather than misfiled as a hang.
- **kill -9**: external `SIGKILL` mid-run (via a background thread once
  `on_spawn` hands back the pid) — classified via `child.signalstatus`,
  distinct from every other "process disappeared" case.
- **hang**: found the *real* way to induce this took two tries. Overriding
  `AUTO_START = false` after `campaign.rc.tmpl`'s forced-on default did
  **not** stick (qw kept playing regardless — whatever it reads that from
  isn't a simple last-write-wins Lua global by the time `ready()` first
  fires; not fully root-caused, not worth chasing further since a cleaner
  option existed). Switched to a from-scratch rc with no `qw.lua` include
  at all — `combo=` is crawl-native and still drives non-interactive
  chargen, but with no `ready()` hook defined nothing ever sends another
  key, so the pty genuinely goes quiet post-chargen. This surfaced a real
  second bug: the hang path's graceful-save attempt (Ctrl-S) calls
  `save_game(true)`, which **exits the process after saving**
  (`files.cc:2603`) — a plain save doesn't touch the logfile, so the
  original code misrouted that EOF into `invalid_telemetry`. Fixed: EOF
  observed while the grace-save is in flight now classifies `timeout_wall`
  directly. All three drills pass after the fix; full writeup in
  `docs/decisions/006-runner-terminal-status-classification.md`.

Also spot-checked `runner.py` against real (non-drilled) play: a normal
run died correctly (`ktyp=mon`, killer `Natasha`, classified `died`) in
3.6s wall time, with both `manifest.json` and `result.json` written.
Re-ran `sampler-test.py` and `rc-gen-test.py` after the `rc-gen.py`/
`campaign.rc.tmpl` changes (new `--turn-budget`/`__TURN_BUDGET__`
plumbing, defaulted to 0/disabled for existing callers) — both still pass
unchanged.

**Result:** Phase 1 now has three tested, independent pieces: the sampler,
rc generation, and the runner state machine (write-ahead accounting +
turn-budget/hang/wall-cap enforcement + all ten §6 terminal statuses
reachable and correctly classified, three drills passing). **Not yet
built:** the collector (reconciling `manifest.json`/`result.json` pairs
across a campaign into SQLite) and the outcome-vector report — these are
what turn a pile of per-run JSON files into the ≥500-game campaign PLAN.md
requires for "running success." Phase 0 still has its two long-open items:
throughput report (campaign still running, unattended across this entire
session, no completions signal seen yet in the block-buffered log) and
rune-milestone verification (still deferred, unchanged status).

Checked the probe one final time before ending this entry: still alive at
~48 min elapsed, still within the ~94 min worst case. **Leaving it running
across this session boundary again** — this is now its fourth session
running unattended; if a future session finds it still going past ~100 min,
that itself is worth investigating (possible stall) rather than assuming
it's still just slow.

**Update, same session:** the throughput probe finished (`data/throughput-report.json`
appeared) while writing up the entry above — did not need to wait for a
future session. Results: 50 games, 900s safety cap, 8 workers — wall_secs
median **87.95s**, p95 **2650s** (inflated by censoring: 23/50, 46%, hit the
900s cap without dying/quitting rather than genuinely taking that long);
user_cpu_secs median 6.17s/p95 72.07s; max_rss_mb median/p95 ~79MB (crawl is
cheap on memory — RAM was never going to be the fleet-sizing constraint,
CPU/wall-clock is). `rune_milestone_count=0` across all 50 — consistent
with the prior session's finding that reaching a rune needs real depth a
900s-capped sample mostly doesn't reach; per the standing guidance from that
entry, **accepting this as "rune verification deferred to Phase 1 campaign
data, not a Phase 0 blocker"** rather than spending a third synchronous probe
on it. Folded the wall/hang numbers into `runner.py`'s
`DEFAULT_WALL_CAP_SECS`/`DEFAULT_HANG_SECS` comments (values themselves
unchanged — 1800s/120s already sat in a reasonable place relative to this
data) and committed the report alongside this entry.

**Phase 0 exit criteria — final status, all five now satisfied:**
reproducible build ✓, telemetry test (exact fields) ✓, canary suite (8/8) ✓,
sampler support-set diff empty ✓, throughput report ✓ (this entry). Phase 0
is **closed**. Rune-milestone exact-field verification specifically is the
one item carried forward as accepted-fallback rather than fully resolved
(logfile-row-only framing, same as death already was per decision 005) —
not re-opened unless a future campaign's data makes it easy to fold in
opportunistically.

**Next step:** Build the collector: glob `data/runs/*/manifest.json` vs
`*/result.json` into SQLite (the reconciliation invariant from §6 — a
manifest with no result is exactly the "crashed with no row, never silently
dropped" case), plus the outcome-vector report with stratified tables (§1).
Once the collector exists, a real campaign driver (parallel `runner.py`
invocations across sampled characters, writing into `data/runs/<run_id>/`,
mirroring `throughput-probe.py`'s `ProcessPoolExecutor` pattern but calling
`runner.run_game()` instead of the ad-hoc `/usr/bin/time` wrapper) is the
last piece before the ≥500-game campaign that's Phase 1's actual exit
criterion — parallel-isolation (N workers, zero cross-contamination) should
be checked directly on that campaign, since per-run directory isolation is
already built into `rc-gen.py`/`runner.py` by construction but hasn't been
verified under real concurrent load yet. The campaign driver will also need
an actual turn-budget number decided (still open — this session's
throughput data only measured wall-clock, not turns; a quick way in: sample
final `turn=` fields from a handful of the `data/runs/` results once the
collector/driver exist, rather than guessing one up front).

## 2026-08-12 — Collector + outcome-vector report built and tested

**Did:** No long-running campaigns were left in flight from prior sessions
(checked `ps`/`logs/` first — nothing running, throughput report already
committed). Built the last Phase-1 piece before the real ≥500-game campaign.

Read the actual `manifest.json`/`result.json` shapes `ops/runner.py` writes
(re-derived from source rather than assumed) and confirmed the milestones
file path convention (`<workdir>/saves/saves/milestones-seeded`, same
double-`saves/` nesting as the logfile) by cross-reading
`ops/telemetry-test.py`. Grepped every `mark_milestone(...)` call site in
the pinned crawl source to get the exact type strings PLAN §1's per-branch
vector needs: `br.enter` (branch entered) and `br.end` (branch end reached,
distinct from `br.exit` which just means "left" — the plan's exact phrase
"branch end reached" maps to `br.end`, not `br.exit`) — this is a fact I
would otherwise have guessed wrong. Confirmed logfile-row field names
straight from `hiscores.cc`: `xl`, `urune` (present only when >0, defaults
to absent/0 otherwise — collector coalesces that), `sc` (score), `turn`.

PLAN §1 requires stratifying by "species, background, and archetype" but
never defines archetype — invented one from objective fields in the pinned
`job-data.h` (has starting spells × has a weapon choice → caster/hybrid/
melee/utility, covers all 25 current jobs with no leftovers) rather than
from memory of general DCSS lore, and wrote up the reasoning and the
rejected alternative (deferring the field entirely) in
`docs/decisions/007-archetype-classification.md`.

Built `ops/collector.py`: `build_db(runs_dir, db_path, strict=False)` does a
from-scratch SQLite rebuild (JSON files are the source of truth, not the
DB, so no incremental-update state to get out of sync) with two tables
(`runs`, `milestones`). The reconciliation invariant (§6: "every scheduled
run appears exactly once with a terminal status") is enforced by
construction — every `manifest.json` found produces exactly one `runs` row.
A manifest with no `result.json` is *not* automatically a failure: since no
PID is recorded, "still running" and "runner process was killed externally"
look identical from outside, so it's split by a grace-period heuristic off
the manifest's own `started_at`/`wall_cap_secs`/`hang_secs` (+ a fixed
buffer for teardown overhead) into `pending` (excluded from the invariant)
vs. `harness_failure` (counted, attributed, never dropped). `--strict`
(for a campaign driver that already knows every worker has exited)
collapses the ambiguity: nothing stays `pending`. Species/background are
decoded from the sampled combo against `data/manifests/legal-characters.json`,
keyed by the run's own `crawl_commit` so a future re-pin mismatch warns
loudly instead of silently mislabeling.

Built `ops/report.py`: `generate(db_path)` is a pure function of the DB
(no wall-clock reads, every dict/list sorted) producing the §1 outcome
vector — terminal-status distribution, win/rune rates, rune-count
distribution, XL/score/turns percentiles, per-branch entered/end-reached
rates (from the `milestones` table, not just the single final logfile row,
which only has the *last* place visited), and death-cause counts — broken
out overall and by each of species/background/archetype per §1's
stratification requirement.

Built `ops/collector-test.py` (Phase 1 exit-criterion test): four synthetic
run fixtures (a won run with 3 runes and a Lair enter+end, a died run, a
genuinely-recent pending run, and a stale run past its budget+grace) —
verifies the reconciliation invariant holds in both strict and non-strict
modes with the right counts in each, stratification correctness
(species/background/archetype buckets contain exactly the expected runs),
and report byte-identical reproducibility (`report.generate()` called twice
against an unchanged DB produces identical JSON text). Deliberately uses
hand-built fixtures rather than a real campaign — this tests the
collector/report logic itself; `runner-drills-test.py` and this session's
own spot-check (below) already prove `runner.py` produces exactly this
manifest/result shape against the real binary. **Passes.**

Fixed one bug while building it: the `runs` table has 31 columns but the
first INSERT used a 29-`?` placeholder string (silent miscount, caught
immediately by `sqlite3.OperationalError`, not a logic bug that could have
passed silently) — replaced with a generated `",".join(["?"] * 31)` so the
placeholder count can't drift from the column count again.

Spot-checked end-to-end against a real (non-synthetic) run: ran
`ops/runner.py` once against the live pinned binary (`char_seed=42`,
sampled `CoAl` — Coglin Alchemist), fed its real `manifest.json`/
`result.json` through `collector.py`/`report.py`, and confirmed the decoded
species/background/archetype (`Coglin`/`Alchemist`/`caster`) and the
death-cause/XL/turn numbers in the report matched the run's actual logfile
row by hand inspection. Scratch dirs were in `/tmp`, not committed.

**Result:** Phase 1 now has all four building blocks: sampler, rc
generation, runner state machine, and collector+report — each independently
tested against the real pinned binary or, for the collector/report (which
don't need crawl at all to test their own logic), against realistic
synthetic fixtures plus one real spot-check. **Not yet built:** the actual
campaign driver (parallel `runner.py` invocations at scale, writing into
`data/runs/<run_id>/`) and the real ≥500-game campaign itself — everything
up to this point has been machinery, not a completed campaign. No
long-running process was started this session (nothing to leave running
across the boundary).

## 2026-08-12 — Campaign driver + isolation test built; turn-count pilot running

**Did:** No long-running jobs were left from prior sessions (checked
`ps`/`logs/` first — clean). Built `ops/campaign.py`, the last missing
Phase 1 piece: a `ProcessPoolExecutor` driver over `runner.run_game()`
(mirrors `throughput-probe.py`'s pattern but drives the real state machine
instead of a bare `/usr/bin/time` wrapper), writing each run into its own
`data/runs/<run_id>/` directory. `run_id` is deterministic in
(`--run-prefix`, `--index-start` + i), which makes the driver resumable by
construction: re-invoking with the same args skips every run_id that
already has a `result.json`, and safely retries any that only got as far as
`manifest.json` (interrupted mid-run) by moving the stale directory aside
first rather than letting crawl resume into the existing save under the
same `-dir`/`-name` — that would silently violate §6's "no resume into
metrics".

Built `ops/campaign-test.py`, the Phase 1 "parallel-isolation test with N
workers shows zero cross-contamination" exit criterion: ran 12 real
concurrent games (6 workers, `--turn-budget 25` so it finishes in ~10s) and
asserted, per run — manifest/result `run_id` matches its own directory;
char_seed/game_seed unique across the batch; the sampled character in
`manifest.json` exactly reproduces `combos.sample_character(char_seed)`
standalone (would diverge under a cross-write); and no file anywhere under
one run's directory tree mentions another run's run_id (the concrete
signature of leaked save/rc data). Also asserted a resume pass launches
nothing and skips all 12. Hit one real bug while building it: the test
loads `campaign.py` dynamically via `importlib.util.module_from_spec`
without registering it in `sys.modules`, and `ProcessPoolExecutor` pickles
submitted functions by (module name, qualname), resolved via `sys.modules`
in the submitting process — every one of the first run's 12 tasks came back
`harness_failure` with `wall_secs=None` immediately (not a real game
failure, a pickling failure) until fixed with an explicit
`sys.modules["campaign"] = campaign` before `exec_module`. `campaign.py`
itself didn't hit this when run directly, since as `__main__` it's already
registered under that name — only mattered for a test importing it as a
library. Reran after the fix: **PASS**, 12/12 self-consistent, zero
cross-contamination, resume pass replayed nothing. Committed and pushed
(`dddc69e`).

**Turn-budget decision, still open — this is now the pilot in flight:**
PLAN §6 wants the per-run cap to be a turn/action budget, not wall-clock
(wall-clock caps make host load and policy speed an evaluation confound),
but no turn-count data exists yet — Phase 0's throughput probe measured
only wall-clock. Started a pilot campaign, `turn_budget=0` (disabled) so
games run to their own natural end (death/quit) or the wall safety cap,
purely to sample real `turn=` values to pick a sensible budget from:

    nohup python3 ops/campaign.py --n-games 40 --workers 10 --turn-budget 0 \
      --wall-cap-secs 900 --run-prefix pilot-turns --runs-dir data/runs \
      --out data/pilot-turns-summary.json > logs/pilot-turns-campaign.log 2>&1 &

PID **28802** (disowned), confirmed running 3s in. 10 workers of 24 CPUs
(leaves headroom per `CLAUDE.md`). Using the Phase 0 throughput-report
numbers as a rough estimate (46% of games hit a 900s cap rather than dying
naturally, out of 50 at 8 workers) this should take roughly ~25-35 min
wall-clock for 40 games at 10 workers — not started blocking on it, moving
to other work while it runs.

**Result:** Phase 1 now has all five building blocks: sampler, rc
generation, runner state machine, collector+report, and campaign driver —
each independently tested. The only remaining gap before the real
≥500-game campaign is picking a turn-budget number, which the pilot above
is collecting data for. No committed campaign data exists yet
(`data/runs/` only has this pilot's still-in-flight `pilot-turns-*` dirs,
not committed — they're intermediate pilot data, not the real campaign).

**Update, same session — pilot contamination found, root-caused, fixed,
relaunched clean:** Rather than idle-wait on the pilot (PID 28802), used
the window to (a) verify Phase 1's "god policy v0" deliverable and (b) build
the §7 fairness probe test — both real, useful, independent work (see the
two entries below), each committed separately. But doing that work meant
running my *own* concurrent crawl+qw processes (several
`fairness-probe-test.py` debug iterations, a `campaign-test.py` run) on the
same machine *while* the 10-worker pilot was also running in the
background — exactly the kind of self-inflicted contention `CLAUDE.md`'s
"leave headroom" guidance is meant to prevent, and it bit here even though
raw CPU headroom existed (24 cores, only ~17 processes peak).

Caught it before trusting the data: checked pilot progress and found **all
30 completed runs classified `timeout_wall` with a near-identical
`wall_secs` (~248-250s) and `output_bytes` around 2KB** (i.e. essentially
zero pty output past the initial Welcome banner, for every single sampled
character regardless of species/class) — far too uniform to be organic
per-character gameplay variance, and 248s matches the hang path's own
arithmetic almost exactly (120s hang detect + up to another 120s grace-save
window + overhead). Investigated rather than assumed a runner bug:
- A single isolated manual replay of the *exact same* character/seed
  (`char_seed=0` → `FeFi.unarmed`, `game_seed=500000`) died naturally in
  1.2s with 415KB of real output — so the rc/character/turn_budget=0
  combination is not inherently broken.
- A clean re-run of `campaign.py` with the same seeds at **2 workers**: all
  4 died normally, no hangs.
- A clean re-run at **10 workers** (matching the pilot): 9/10 died
  normally, 1 `lua_error` — no hangs either.

Both clean re-tests (including at the pilot's own worker count) came back
healthy once nothing else was competing for the machine, which points at
transient contention from my own concurrent foreground work during the
original window, not a `campaign.py`/`runner.py` defect. Discarded the
contaminated `data/runs/pilot-turns-*` (all 30, deleted, plus the debug
scratch dirs in `/tmp`) rather than trying to salvage or use any of it — it
would only skew the turn-count distribution this pilot exists to measure.

**Relaunched clean**, same command as originally, and this time deliberately
not running other crawl-spawning work in the foreground while it's up:

    nohup python3 ops/campaign.py --n-games 40 --workers 10 --turn-budget 0 \
      --wall-cap-secs 900 --run-prefix pilot-turns --runs-dir data/runs \
      --out data/pilot-turns-summary.json > logs/pilot-turns-campaign.log 2>&1 &

PID **30813** (disowned), confirmed running.

**Result:** Phase 1 building blocks unchanged from the prior entry (all
five pieces done and tested) plus two more real pieces landed this session:
god policy v0 verified as already satisfied by qw's own defaults
(`docs/decisions/008`, no code change needed), and a live fairness probe
for the §7 monster-visibility claim (`ops/fairness-probe-test.py`,
`docs/decisions/009`) — found the API's bounds guarantee is stronger than
PLAN's own description (a hard Lua error beyond LOS radius, not just a nil),
and hit + fixed a real `crawl.mpr()` message-loss bug along the way (fixed
via `crawl.stderr()`). Turn-budget is still the one open item, now
correctly in flight on clean data.

**Next step:** Check `ps -p 30813` / `logs/pilot-turns-campaign.log` /
`data/pilot-turns-summary.json`. **Do not run other crawl-spawning
processes in the foreground while it's up** — that's exactly what
contaminated the first attempt. Once done (or partially done — per-run
`data/runs/pilot-turns-*/result.json` files land incrementally): run
`ops/collector.py --runs-dir data/runs --db /tmp/pilot.db` (a scratch DB,
don't overwrite `data/campaign.db`) and `ops/report.py --db /tmp/pilot.db`,
and read the `turns_survived` percentiles for `died`/`quit_stuck` runs
(natural ends only — exclude `timeout_wall`, whose turn count is censored,
not a real endpoint). Before trusting the numbers this time, sanity-check
`output_bytes`/`wall_secs` aren't suspiciously uniform across runs the way
the contaminated batch was. Pick a turn-budget (e.g. somewhat above p95)
and record it + reasoning in `docs/decisions/010-turn-budget.md` (009 is
now taken by the fairness-probe-scope note). Delete/don't commit the
`pilot-turns-*` run directories once the number is extracted — throwaway
calibration data, not campaign data. Then launch the real campaign with
`--turn-budget <chosen>`, a `--run-prefix` distinct from `pilot-turns`,
sized for ≥500 games, **started detached** with PID/log recorded here
before it's kicked off — and this time, once it's running, actually leave
it alone rather than doing more concurrent crawl-spawning work in the same
session; use the wait for genuinely CPU-light work only (docs, review,
reading), or just end the session and let it run. After it completes (or
enough of it has, on a later session), run `collector.py --strict` +
`report.py` and commit `data/campaign.db` + the generated report — that
combination is Phase 1's "running success for the project" per
`PROMPT.md`.

**Next step (superseded by the entry above — kept for history only):**
Build the campaign driver: a `ops/campaign.py` (or similar)
that mirrors `ops/throughput-probe.py`'s `ProcessPoolExecutor` pattern but
calls `runner.run_game()` for real (turn-budget-bearing) runs across N
sampled characters, writing each into its own `data/runs/<run_id>/`
directory, with `char_seed` drawn from a dedicated counter/RNG stream
(never reusing `game_seed`, per §2) — this is what actually produces the
≥500-game campaign data Phase 1's exit criterion needs. Before or alongside
it, decide the turn-budget number (still genuinely open — only wall-clock
was measured in the Phase 0 throughput probe): a cheap way in is to sample
`turn=` from a first small batch of real `data/runs/` results via
`ops/collector.py`+`ops/report.py` (now built) and pick a budget from that
distribution, rather than guessing one before any data exists. Once the
driver exists and turn-budget is chosen: run the parallel-isolation check
(N concurrent workers, assert zero cross-contamination — directory
isolation is already correct by construction in `rc-gen.py`/`runner.py` but
unverified under real concurrent load) as part of launching the real
≥500-game campaign, started **detached** per `CLAUDE.md` since it will run
for hours, with the PID/log path recorded here *before* starting it.

## ORCHESTRATOR REVIEW — 2026-08-12

**Assessment.** Phase 0 is genuinely closed — every exit criterion is backed
by a real acceptance test (exact-field telemetry assertions, 8/8 canaries,
live support-set diff, throughput report), not existence checks. Phase 1 has
all five building blocks built and individually tested (sampler, rc-gen,
runner state machine + drills, collector/report, campaign driver + isolation
test); its remaining exit criterion is the real ≥500-game campaign, blocked
until now on the turn-budget pilot. Decisions 003–009 are sound and
source-cited; no architectural drift from PLAN.md found; no BLOCKED.md
needed; fairness contract intact (probe test live-verifies the LOS boundary;
nothing leaks seed/save/map state into a policy path). Statistical integrity
(§8) not yet at risk — no Phase 2 tuning has begun.

**Critical finding — the pilot contamination was NOT host contention; the
prior entry's diagnosis was wrong.** The relaunched pilot (PID 30813)
reproduced the identical signature with an idle machine: every completed run
`timeout_wall` at ~247s with ~2KB of output. Root cause, proven by A/B
repro: `rc-gen.py`'s `write_run_dir()` returned `clo_args` whose
`-rc/-dir/-morgue` paths were *relative* whenever the caller's `workdir` was
relative (the pilots used `--runs-dir data/runs`), while
`runner.monitor_game()` spawns crawl with `cwd=workdir` — so crawl resolved
`-rc data/runs/<id>/run.rc` against `.../data/runs/<id>/`, never found the
rc, never loaded qw, and sat silently at the welcome screen until hang
detection killed it (the nested `data/runs/<id>/data/runs/<id>/morgue` debris
in each run dir was the tell). Same char/seed: relative workdir → 247s hang
with 2,179 bytes; absolute → normal death in 3.6s with 415KB. Every "clean
re-test" that passed had used an absolute (`mkdtemp`/`/tmp`) runs dir —
including `campaign-test.py` itself — which is exactly why the wrong
contention theory survived: the discriminator was path shape, not load, and
foreground games run *during* pilot #1 all worked (more disproof of
contention nobody noticed).

**Corrections applied directly (small, unambiguous):**
1. `ops/rc-gen.py` — `write_run_dir()` now resolves `workdir` to absolute
   before building paths/`clo_args`; docstring records the bug.
2. `ops/runner.py` — `run_game()` resolves `workdir` the same way
   (manifest/result/cwd stay consistent for any caller).
3. `ops/campaign-test.py` — first campaign pass now deliberately drives a
   *relative* runs_dir (`os.path.relpath` of the mkdtemp dir) so this
   regression stays covered; resume pass keeps the absolute shape. Re-ran:
   **PASS** (12/12 real games, zero cross-contamination, resume clean).
   Single-run repro via relative workdir also re-verified: dies normally.
4. Killed the garbage pilot (PID 30813) and deleted all contaminated
   `data/runs/pilot-turns-*` dirs (both batches were 100% invalid — the
   first batch's data was equally garbage; contention was never the cause).

**Corrections for the next worker iterations:**
1. Relaunch the turn-budget pilot with the fixed code — same command as the
   last entry (`nohup python3 ops/campaign.py --n-games 40 --workers 10
   --turn-budget 0 --wall-cap-secs 900 --run-prefix pilot-turns --runs-dir
   data/runs --out data/pilot-turns-summary.json > logs/pilot-turns-campaign.log
   2>&1 &`), record the PID before starting. Sanity-check early results:
   statuses should be mixed (mostly `died`), wall_secs varied, output_bytes
   in the hundreds-of-KB range — NOT uniform ~247s/~2KB.
2. The prior entry's "do not run other crawl-spawning processes while the
   pilot is up" rule was derived from the wrong diagnosis. Moderate
   concurrent work is fine (it always was); keep total load within
   CLAUDE.md's headroom guidance, nothing stricter.
3. Do not add `-no-throttle` to `clo_args` if you notice PLAN §5 lists it:
   verified this session that non-DGAMELAUNCH builds default
   `throttle(false)` (`state.cc:48-53`) — the flag is moot for our build.
   Recorded here so it isn't cargo-culted in later.
4. Nit, no action needed on existing files: two decision files share number
   003 (a concurrent-session collision). Take the next free number (010 is
   reserved by the prior entry for turn-budget) and keep numbers unique.

**Next step:** unchanged in substance from the prior entry, now unblocked:
relaunch the pilot (correction 1 above), extract `turns_survived`
percentiles from natural-end runs via a scratch collector DB, record the
chosen turn budget in `docs/decisions/010-turn-budget.md`, delete the pilot
run dirs, then launch the real ≥500-game campaign detached with the chosen
`--turn-budget` and a distinct `--run-prefix`, PID/log journaled before
launch.

## 2026-08-12 — Pilot found dead-on-arrival this session; relaunched with setsid; investigating non-survival separately from the earlier contamination bug

**Did:** Started this session by checking the prior entry's pilot (PID
30813, launched via plain `nohup ... &` without `disown`/`setsid`) per
`CLAUDE.md`/`PROMPT.md`'s "check logs for unresolved long-running jobs
first" step. Found it **not running** (`ps -p 30813` empty) and **zero
progress**: `logs/pilot-turns-campaign.log` contains only the startup
banner line ("40 run(s) to launch...") with no per-game completion lines,
no traceback, no exception; `data/runs/` is completely empty (not even a
stale `manifest.json`-only directory from an interrupted first game).
`data/pilot-turns-summary.json` never got written.

This is a **different failure mode than the relative-path contamination**
the orchestrator review found and fixed (`642e3ec`) — that pilot ran to
completion and produced 30 *classified-but-wrong* results; this one
produced **no results at all**, meaning either the process never
progressed past printing the launch banner, or it was killed near-
immediately afterward. Checked for a machine reboot as the simple
explanation (`nohup` alone doesn't protect against the whole VM stopping):
`uptime -s` / `/proc/uptime` put boot at 08:03:55, while the log file's
birth time is 09:56:00 and last-modified 10:12:38 — both comfortably after
boot, so **no reboot occurred**; the process died mid-boot-session for some
other reason. Checked `dmesg`/`journalctl -k` for an OOM kill or similar
around that window — nothing (though `journalctl` warned it can't see
system-wide messages as a non-adm user, so this check has limited power).
No cgroup `pids.max`/`memory.max` file found to check a hard limit against.
Not fully root-caused — recording the negative results rather than
guessing further, since the machine itself gives no evidence either way and
chasing it further would trade real progress for speculation.

**Working theory (unconfirmed):** the original launch command was
`nohup python3 ... &` with no `disown` and no `setsid` — if the harness's
Bash-tool session boundary does something stronger than SIGHUP to a
command's process group when a turn/session ends (e.g. killing the whole
group rather than just closing the controlling terminal), plain `nohup`
would not save it, while the earlier throughput probe (PID 21247, which
*did* survive across several session boundaries per this journal) might
have differed in some way not yet identified — worth comparing exact launch
commands if this recurs. Not spending more time on the theory now; instead
hardening the relaunch against it directly.

**Relaunched** with `setsid` (new session, immune to controlling-terminal/
job-control signals from this Bash session specifically) in addition to
`nohup` and explicit `disown`, stdin redirected from `/dev/null`:

    setsid nohup python3 ops/campaign.py --n-games 40 --workers 10 --turn-budget 0 \
      --wall-cap-secs 900 --run-prefix pilot-turns --runs-dir data/runs \
      --out data/pilot-turns-summary.json > logs/pilot-turns-campaign.log 2>&1 < /dev/null &
    disown

Confirmed alive 2s later: main driver **PID 33276** (parent PID 329, i.e.
already reparented off this shell) with 10 live worker children
(33277-33286). Log path unchanged: `logs/pilot-turns-campaign.log`;
summary path unchanged: `data/pilot-turns-summary.json`. `data/runs/` was
already empty (nothing to clean up from the dead attempt).

**Result:** No campaign data collected yet for a third session running —
still the same open item (turn-budget pilot) as the last two entries, now
relaunched with a more robust detach method. Will check progress within
this same session (not just defer to a future one) before deciding whether
`setsid` actually fixed survivability or whether this needs escalating to
`docs/BLOCKED.md` as an environment limitation.

**Next step:** Check `ps -p 33276` and `tail logs/pilot-turns-campaign.log`
— expect to start seeing `[N/40] pilot-turns-NNNNNN status=... wall=...s`
lines within the first couple minutes if it's healthy this time (contrast
with the dead run, which never printed a single one). If it dies again with
the same zero-progress signature, that's strong evidence against the
"my Bash session teardown" theory (since `setsid` should specifically
defeat that) and worth escalating: try running it via a fully separate
mechanism (e.g. `at now`, or a systemd user unit/transient scope via
`systemd-run --user`) rather than shell job control at all, and if that
*also* silently dies, write `docs/BLOCKED.md` describing the exact symptom
(process disappears with no log output, no core, no dmesg/journalctl
evidence) since at that point it's a genuine environment question, not a
harness bug — per `CLAUDE.md`, keep working on whatever isn't blocked
(there is no other Phase 1 item left, so idle time should go to re-verifying
existing tests still pass / doc cleanup rather than sitting idle) while
this is sorted out. If it does survive and completes: same extraction steps
as the last two entries (collector+report on a scratch DB, pick a turn
budget from `turns_survived` percentiles of natural-end runs, record
`docs/decisions/010-turn-budget.md`, delete pilot run dirs, launch the real
≥500-game campaign with the chosen budget, detached the same hardened way).

## 2026-08-12 (cont.) — Pilot survived with setsid hardening; turn budget chosen; real ≥500-game campaign launched

**Did:** Checked on the pilot relaunched earlier this session (PID 33276,
`setsid nohup ... & disown`). It **survived and completed**: process exited
cleanly, all 40/40 runs produced `result.json` in ~161s. This confirms the
working theory from the prior entry — plain `nohup ... &` without `setsid`
did not survive this harness's session/turn boundary, `setsid` does. Every
future detached launch in this project should use the same
`setsid nohup ... > log 2>&1 < /dev/null & disown` form.

Sanity-checked the pilot data wasn't a repeat of the earlier relative-path
contamination bug (642e3ec) before trusting it: 40/40 unique `char_seed`
values, manifest `run_id` matches its directory name for all 40 — clean.
Ran `ops/collector.py` against it into a scratch DB: `n_reconciled: 40,
n_pending: 0, n_harness_failure_missing_result: 0, invariant_holds: true`.

Outcome mix (n=40): 32 `died`, 4 `lua_error`, 2 `quit_stuck` (qw's own
QUIT_TURNS at turn 8000/9000), 2 `timeout_wall` (both the 120s hang path,
not the literal 900s cap — no run hit that in this pilot).
`turns_survived` over the 34 natural-end (`died`+`quit_stuck`) runs:
median 1015, p95 9595, max 11794. Confirmed `lua_error` is a real,
distinctly-classified PLAN.md §6 terminal status, not a harness defect, and
doesn't count against the invalid-run-rate target (that's
`invalid_telemetry`/`harness_failure`); left as a Phase-2-relevant
observation, not a Phase 1 blocker, per CLAUDE.md ("adapt with the smallest
working alternative... do not stop to renegotiate").

Recorded the choice in `docs/decisions/010-turn-budget.md`:
**`--turn-budget 20000`** (~2.1x pilot p95, ~1.7x observed max — generous on
purpose since under-budgeting biases the outcome report by misclassifying
real deaths/quits as `timeout_turns`; turns/s accelerates sharply with game
depth in this data, so the generous cap costs at most tens of seconds of
extra wall-clock even for outlier survivors). `--wall-cap-secs 900` and
`--hang-secs 120` kept at their existing defaults as the operational
backstops under the turn budget.

Deleted the pilot artifacts (`data/runs/pilot-turns-*`,
`data/pilot-turns-summary.json`, scratch `/tmp` DB/report) — not part of
the campaign deliverable.

**Launched the real Phase 1 campaign**, detached with the confirmed-working
hardened form:

    setsid nohup python3 ops/campaign.py --n-games 500 --workers 16 \
      --turn-budget 20000 --wall-cap-secs 900 --run-prefix phase1-500 \
      --runs-dir data/runs --out data/phase1-500-summary.json \
      > logs/phase1-500-campaign.log 2>&1 < /dev/null &
    disown

16 workers chosen (of 24 CPUs) to leave headroom per `CLAUDE.md`. Confirmed
alive: driver **PID 34524** with 16 live worker children (34525-34540,
already reparented off this shell — parent no longer this session's bash).
Log: `logs/phase1-500-campaign.log`. Summary (on completion):
`data/phase1-500-summary.json`. Runs land in `data/runs/phase1-500-*`
(gitignored via the `runs/` pattern).

**Result:** Real ≥500-game Phase 1 campaign running unattended. This is the
"running success for the project" campaign PROMPT.md Phase 1 names.

**Next step:** On a future invocation (or later this session if time
allows), check `ps -p 34524` / `tail logs/phase1-500-campaign.log` /
`data/phase1-500-summary.json`. If complete: run `ops/collector.py
--runs-dir data/runs --db data/phase1-500.db` (this time a **committed**
DB, not scratch) and `ops/report.py --db data/phase1-500.db --out
data/phase1-500-report.json`, then check the Phase 1 exit bar precisely:
reconciliation invariant holds, invalid-run rate
(`invalid_telemetry`+`harness_failure` share) <2%, report reproduces
byte-identically on a second run against the same DB. If all pass, Phase 1
is exit-complete per PROMPT.md and the next session should move to Phase 2
(§8 experiment protocol, first candidate items per PLAN.md §352-359). If
still running: leave it, do not idle-wait — there is no other open Phase 0/1
item, so use idle time for doc cleanup / re-verifying the existing test
suite still passes (`ops/*-test.py`) rather than sitting idle, per
`CLAUDE.md`'s "no invocation with zero trace" rule.

## ORCHESTRATOR REVIEW — 2026-08-12 (second pass) — Phase 1 exit verified on the real campaign; Phase 1 CLOSED

**Assessment.** The phase1-500 campaign (PID 34524, launched last entry with
the setsid-hardened form) completed cleanly: 500/500 runs in ~711s wall at 16
workers, driver exited on its own, summary written. I verified the Phase 1
exit bar directly against the data rather than taking the driver's summary on
faith:

- **Data integrity:** 500 run dirs, 500 unique `char_seed`, 500 unique
  `game_seed`, zero manifest/dir `run_id` mismatches, zero missing
  `result.json`, wall_secs p5/50/95 = 3.8/7.2/130s and output_bytes p5/50/95
  = 27KB/462KB/2.6MB — healthy organic variance, no trace of the 642e3ec
  contamination signature (uniform ~247s/~2KB).
- **Reconciliation invariant (strict):** `ops/collector.py --strict` →
  `n_manifests=500, n_reconciled=500, n_pending=0,
  n_harness_failure_missing_result=0, invariant_holds=true`. DB committed as
  `data/phase1-500.db` (~1MB).
- **Invalid-run rate:** `invalid_telemetry` + `harness_failure` = 0/500 =
  **0%**, target <2%. ✓
- **Report reproducibility:** `ops/report.py` run twice against the DB —
  byte-identical (`cmp` clean). Committed as `data/phase1-500-report.json`.
- **Sampler goodness-of-fit + collector tests re-run at review time:** both
  still PASS.
- Drills and parallel-isolation were already green (`runner-drills-test.py`,
  `campaign-test.py` — the latter re-verified after the 642e3ec fix with a
  deliberately-relative runs dir); the campaign itself is the at-scale
  evidence on top.

**All five §9 Phase 1 exit criteria are satisfied. Phase 1 is closed.** This
campaign is the frozen baseline all Phase 2 claims measure against (PLAN §9).

Baseline outcome vector (n=500): died 441 (88.2%), quit_stuck 28 (5.6%),
lua_error 26 (5.2%), timeout_wall 4 (0.8%), timeout_turns 1 (0.2%); wins 0,
runes 0 (rune_count_distribution {0: 500}). turns_survived (natural ends,
n=469): median 1077, p95 9000, max 10723. XL median 2, max 11. Milestones
flowed for **every** run (500/500 have `begin`; 945 rows total across 12
types incl. `br.enter` 43, `br.end` 4, `god.worship` 48) — the telemetry
pipeline works at scale, so invalid_telemetry=0 is meaningful, not vacuous.

**Findings (recorded, no action needed now):**
1. **Decision 005 refined, not contradicted:** 22 `death` milestones appeared
   — all from Felid runs (non-final life losses; `you.lives` is the Felid
   mechanic). Final deaths still never emit a milestone. Addendum appended to
   `docs/decisions/005`.
2. **Turn budget 20000 validated:** exactly 1/500 hit it (a VSAE at 607s
   wall); natural max was 10723 with no pile-up near the cap. Decision 010's
   revisit clause is not triggered.
3. **lua_error at 5.2%** (26/500, spread across species, Felid 6 highest) —
   consistent with the pilot's rate. This is qw-vs-pinned-crawl breakage in
   legitimately-classified runs, exactly the "failures become Phase 2 items"
   row of PLAN §10. A Phase 2 candidate: sample the `detail` fields from
   these 26 runs to find the dominant qw error(s) before picking other §352
   items — reducing lua_error grows the effective sample for every later
   experiment.
4. **Rune verification stays accepted-fallback:** 0 runes in 500 games, so no
   opportunity to fold in the exact-field rune assertion. Unchanged framing.

**Drift / loops / fairness / stats (§7, §8):** No architectural drift; all
adaptations documented in decisions 002–010. No repeated dead ends — the
three pilot attempts were distinct failures (relative-path bug, session-
boundary kill, then success), each root-caused and journaled. Fairness
contract intact (campaign was pure data collection; probe test unchanged).
§8 not yet at risk, but it becomes live the moment Phase 2 starts: **the
phase1-500 baseline is now frozen — Phase 2 work must not retune or re-run
it, and every claimed improvement needs pre-declared minimum effects and
held-out seeds per §8.** No BLOCKED.md needed.

**Corrections:** none required — the worker's trajectory is sound.

**Next step:** Begin Phase 2 (PLAN §9 "Raise the floor"). First concrete
task: query the 26 lua_error runs' `detail`/output artifacts (dirs still in
`data/runs/phase1-500-*`, gitignored but on disk) to identify the dominant
qw Lua failure mode(s), and write it up as the first Phase 2 hypothesis item
(config-flagged fix + §8 experiment protocol: pre-declared effect, held-out
seeds, baseline = `data/phase1-500.db`). Before any fix work, write the §8
experiment-protocol scaffolding if it doesn't exist yet (seed splits,
pre-declaration file format) — the protocol must exist before the first
experiment, not be retrofitted. Do not delete `data/runs/phase1-500-*` yet;
the lua_error diagnostics need the raw artifacts.

## 2026-08-12 (cont.) — First Phase 2 item: two real qw Lua bugs found, fixed, flagged; experiment running

**Did:** Replayed the 26 `phase1-500` lua_error runs against the pinned
binary to find the actual crash text (not just `runner.py`'s "matched 'Lua
error' in output"). Found replay is **not** exactly reproducible even at a
fixed char/game seed — 2 of 5 replayed runs hit the same crash, 3 instead
played out to an uneventful natural death — most likely un-seeded Lua-level
tie-breaking inside qw itself; not chased further, but means bug-hunting
had to lean on source reading + live console verification, not on trusting
replay to reproduce the original 26 exactly.

The 2 reproducing replays gave 2 distinct, real qw bugs, both confirmed by
reading `vendor/qw/source/*.lua` directly:
1. `equipment.lua`'s `equip_letter_for_item` indexes `inventory_equip()`'s
   result directly; that function's memoization wrapper (`turn_memo_args`)
   caches a `nil` result as `false` (table can't otherwise distinguish
   "uncached" from "cached nil"), so a character with zero equipped items
   (unarmed Felid, etc.) crashes with "attempt to index ... a boolean
   value" the first time a ring or (Coglin) 2h-weapon slot is checked.
2. `plans-rest.lua`'s `should_rest()` references `hostile_servants_timer`,
   a global assigned **nowhere** in qw's source (grepped the whole tree) —
   every Makhleb worshipper crashes here unconditionally, first tick after
   joining.

Fixed both with minimal call-site guards (`patches/qw/0001-fix-lua-errors.patch`,
applied by the existing `ops/fetch-vendor.sh` overlay mechanism), gated by
a new rc-settable `QW_BUGFIX_LUA_ERRORS` flag (default true) so the
original crashes stay reproducible as an experiment control arm — threaded
through `campaign.rc.tmpl` → `rc-gen.py` → `runner.py` → `campaign.py`
(`--disable-bugfix-lua-errors`). Full writeup, source citations, and
alternatives considered in `docs/decisions/011-lua-error-root-cause.md`.

Verified both fixes live against the real pinned+patched binary with
`ops/bugfix-lua-errors-test.py`: drives crawl's wizard-mode dlua console
(`&`, confirm, Ctrl-U) to call the two new guard functions directly and
assert flag-on returns a safe value while flag-off reproduces the original
crash class. Building this hit a real choreography bug worth remembering:
a *second* `&` keypress is not "reopen the wizard command prompt", it's
itself a wizard sub-command (`wizard_list_companions()`) — a blind-timed
version of the drill reliably misfired onto that instead of the console;
fixed by `pexpect.expect()`-ing each prompt's exact text before sending the
next key rather than guessing at timing. **4/4 drills pass.**

`ops/fetch-vendor.sh` re-fetch (to pick up the qw patch) wipes the built
crawl binary along with the vendor dir; rebuilt clean (`EXTERNAL_DEFINES="-DDGL_MILESTONES"
-j18`, ~90s, `logs/crawl-rebuild-qwfix.log`) and confirmed via `-version`
(DGL_MILESTONES + WIZARD present). Re-ran the **entire** existing test
suite after the `rc-gen.py`/`runner.py`/`campaign.py`/`collector.py`
signature changes (new `bugfix_lua_errors` param threaded through all
four, new `bugfix_lua_errors` column in the `runs` table): collector,
sampler, rc-gen, runner-drills, telemetry, campaign-isolation, fairness —
**all still pass unchanged.**

Built `ops/experiment.py`, the PLAN §8 protocol scaffolding the prior
entry flagged as required *before* any Phase 2 experiment: deterministic
hash-based seed splits (`split_seed`/`seeds_for_split` — dev/validation/
holdout, no stored membership list, decorrelated from seed allocation
order so a contiguous seed range doesn't correlate with split membership),
a write-once `Predeclaration` file format (refuses to overwrite — the
whole point of a predeclaration is it's fixed before results exist), and
stdlib-only Wilson score / Newcombe-Wilson interval math for effect-size
comparisons (same "no scipy/numpy" constraint `sampler-test.py` already
worked around). `ops/experiment-test.py`: seed-split determinism/coverage/
disjointness, Wilson intervals cross-checked against a hand-computed
reference (5/20 → (0.1119, 0.4687) — my first attempt used a misremembered
reference value and the test correctly failed until I recomputed it by
hand from the formula), predeclaration write-once + evaluate correctness
on synthetic clear-effect/no-effect cases. **All pass.**

Gave `campaign.py` a `--seeds-file` option (explicit JSON list of
char_seeds, overriding the default contiguous base+n allocation) so an
experiment can drive exactly the seeds `experiment.seeds_for_split()`
selects rather than "the next N in order" — re-ran `campaign-test.py`
after this change, still passes unchanged.

Declared the first real experiment,
`data/experiments/lua-error-bugfix/predeclaration.json`: hypothesis
(the fix reduces `lua_error` rate vs. the frozen phase1-500 baseline,
5.2%), primary outcome `lua_error_rate`, direction decrease, minimum
effect 2 points, alpha 0.05, 300 games/arm, seed_split validation, arms
`control` (`bugfix_lua_errors=false`) / `treatment` (`bugfix_lua_errors=true`),
baseline_ref `data/phase1-500.db`. 300 validation-split char_seeds drawn
from a fresh pool (`3000000..3002999`, disjoint from the baseline's
`0..499`) via `experiment.seeds_for_split`, written to
`data/experiments/lua-error-bugfix/seeds.json`.

Committed and pushed everything above (`3e7d5df`) — **before** launching
the long-running experiment run, per `CLAUDE.md` (caught myself having
launched the campaign slightly ahead of the commit; committed immediately
after rather than continuing further uncommitted work).

**Started detached** (`setsid nohup ... & disown`, the confirmed-working
hardened form): a wrapper script running both arms of the experiment
sequentially (control then treatment, each 300 games via `--seeds-file`,
`--turn-budget 20000 --wall-cap-secs 900 --workers 16`, run prefixes
`exp-luafix-control-`/`exp-luafix-treatment-`) —

    setsid nohup /tmp/run_lua_error_experiment.sh > logs/lua-error-experiment.log 2>&1 < /dev/null &
    disown

Driver **PID 41226**, confirmed alive with 16 live `campaign.py` worker
children for the control arm. Log: `logs/lua-error-experiment.log`.
Per-arm summaries land at
`data/experiments/lua-error-bugfix/{control,treatment}-summary.json`; the
script prints `EXPERIMENT_DONE` on completion. Sequential (not both arms
concurrently), specifically to avoid 32 workers competing for 24 CPUs —
based on phase1-500's throughput (500 games/~711s at 16 workers), expect
very roughly ~7-15 min per arm, more for the control arm since more of its
games will hit the (now-unfixed-again) hang-after-crash path instead of a
clean death.

**Result:** Phase 2's first item (lua_error root cause + fix + config flag
+ regression test + §8 scaffolding) is code-complete and committed. The
experiment measuring its actual effect is running, not yet collected.

**Next step:** Check `ps -p 41226` / `tail logs/lua-error-experiment.log` /
existence of `data/experiments/lua-error-bugfix/treatment-summary.json`
(the last thing the script writes before `EXPERIMENT_DONE`). Once both
summaries exist: run `ops/collector.py --runs-dir data/runs --db
data/experiments/lua-error-bugfix/results.db --strict`, then compute each
arm's `lua_error` count/n from that DB (`WHERE run_id LIKE
'exp-luafix-control-%'` / `'exp-luafix-treatment-%'`), call
`experiment.evaluate_predeclaration` with those counts, and write the
result JSON to `data/experiments/lua-error-bugfix/result.json`. Sanity-
check before trusting the numbers: control-arm `lua_error` rate should be
in the same ballpark as the phase1-500 baseline's 5.2% (it's running the
literal original bug), and status mixes for both arms should look like
organic gameplay variance (varied wall_secs/output_bytes per run), not the
suspiciously-uniform signature that flagged the relative-path pilot
contamination bug earlier in this project. Commit
`data/experiments/lua-error-bugfix/{results.db,result.json,*-summary.json}`
once collected. If the fix clears its predeclared 2pt minimum effect with
the CI excluding zero, write up the result in `docs/decisions/011`'s
follow-up section (or a short addendum) and consider `QW_BUGFIX_LUA_ERRORS`
proven — no code change needed either way since the flag already defaults
to fixed-on. If still running: leave it (detached), do not idle-wait —
there's no other blocking Phase 2 item, so use the wait for light work
(re-reading PLAN §8/§352-359 for the next Phase 2 candidate item after this
one closes) rather than sitting idle.

## 2026-08-12 (session 2) — lua-error-bugfix experiment collected (confirmed); found + fixed a second Phase 2 item (indefinite-transform rest stall); second experiment launched

Picked up from the prior session's Next step: `ops/run_lua_error_experiment.sh`
had finished overnight (`logs/lua-error-experiment.log` ends with
`EXPERIMENT_DONE`; PID 41226 gone). Sanity-checked before trusting the
numbers per the prior Next step's own checklist: control-arm status mix
(228 died / 10 quit_stuck / 9 lua_error / 3 timeout_wall out of the first
250 printed) looked like organic variance, not the uniform-signature
contamination bug from earlier in the project; control-arm lua_error rate
(17/300 = 5.67%) landed close to the phase1-500 baseline's 5.2%, as
expected since it's running the literal unfixed bug.

Ran `ops/collector.py --runs-dir data/runs --db
data/experiments/lua-error-bugfix/results.db --strict`: 1100 manifests
(500 phase1-500 + 300 control + 300 treatment), reconciliation invariant
holds, 0 pending, 0 harness_failure. Queried each arm's `lua_error` count/n
from the DB and ran `experiment.evaluate_predeclaration`: control
17/300 (5.67%), treatment 1/300 (0.33%), diff -5.33pt (95% CI -8.56 to
-2.74) — clears the predeclared 2pt minimum effect with the CI excluding
zero. **`QW_BUGFIX_LUA_ERRORS` confirmed effective**, written up in
`docs/decisions/011`'s new Follow-up/Result section and
`data/experiments/lua-error-bugfix/result.json`. No code change needed
(flag already defaults to fixed-on).

While that ran, used the wait (per the prior Next step's own suggestion —
don't idle, re-read PLAN §8/§352-359 for the next Phase 2 candidate) to
mine `data/phase1-500-report.json`'s `by_background` stratification rather
than starting from PLAN's example list blind: one background,
**Shapeshifter, was 28/28 (100%) `quit_stuck`** — a complete, dead bucket,
not a rare failure mode. Dispatched a research subagent to read qw's and
crawl's source and confirm the mechanism before writing any fix (kept it
read-only, no code, per the "delegate research, do the writing yourself"
discipline) — it came back with an exact file:line root cause, independently
reproducible by hand-reading the same files afterward:

`should_rest()`/`reason_to_rest()` (`plans-rest.lua`) both do a bare
`or transformed()`, written for genuinely-transient spell forms (expire on
their own, so eventually make `transformed()` false again). But
`you.transform()` for a talisman-driven form (`beast`, `flux`, `blade`,
`statue`, `snake`, `dragon`, `death`, `storm`, `maw` —
`form-data.h`'s 9 entries with a real `talisman_type`) never expires on its
own; it only ends via "Begin Untransformation". Shapeshifter starts
talisman-locked into beast-form at character creation, so `transformed()`
is permanently true, `should_rest()` is permanently true, and
`plans.rest` (ahead of `plans.explore`/`explore2` in the master cascade)
fires every tick forever — confirmed against every sampled Shapeshifter
run in phase1-500 (`-000015`, `-028`, `-047`, `-053`, `-054`: identical
signature, turn counter racing to 8-9k while wall-clock stays ~17-30s, 0
kills, still on D:1, still beast-form, death/quit via the 0.32
"power of Zot" camping-punishment HP drain). Not Shapeshifter-specific in
mechanism — any character transforming mid-game via one of the 9 talismans
would hit the same trap.

Fixed with the same minimal-call-site-guard shape as decision 011's two
fixes: `qw_transform_is_indefinite(transform_name)` (name-table lookup
against the 9 talisman `wiz_name`s, optional explicit-name override for
direct testability) + `qw_transformed_worth_resting_for()`, replacing both
`or transformed()` call sites (`transformed()` itself untouched — still
correct at its other, genuinely-transient-form call sites elsewhere in qw).
Write-up with full source citations and alternatives considered in
`docs/decisions/012-indefinite-transform-rest-stall.md`. New patch
`patches/qw/0002-fix-indefinite-transform-rest.patch`, verified it applies
cleanly in sequence after `0001-fix-lua-errors.patch` against a fresh
pristine checkout and byte-matches the working tree (scratch-repo test, not
committed). Regenerated `vendor/qw/qw.lua` via `make-qw.sh` (no crawl
rebuild needed — pure-Lua change, and `ops/fetch-vendor.sh`'s
`bash make-qw.sh` step is the only regen crawl actually loads).

New rc-settable flag `QW_BUGFIX_INDEFINITE_TRANSFORM` (default true),
threaded through the identical chain as `QW_BUGFIX_LUA_ERRORS`:
`campaign.rc.tmpl` → `rc-gen.py` → `runner.py` → `campaign.py`
(`--disable-bugfix-indefinite-transform`) → `collector.py` (new
`bugfix_indefinite_transform` DB column). Deliberately a separate flag, not
folded into `QW_BUGFIX_LUA_ERRORS`: independent hypotheses, and the
existing lua-error-bugfix experiment's control arm should keep reproducing
exactly its own two crashes, nothing else.

New drill test `ops/bugfix-indefinite-transform-test.py`, same wizard-mode
dlua-console choreography as `ops/bugfix-lua-errors-test.py` (expect()
each prompt's exact text, not blind timing): calls
`qw_transform_is_indefinite(name)` directly by name against the real
pinned+patched binary — `"beast"`/`"flux"` → true, `""`/`"spider"` → false,
confirmed both with the flag on and off. **5/5 drills pass.** Re-ran the
full existing test suite after the five-file signature change (rc-gen,
runner, campaign, collector, plus the new campaign.rc.tmpl placeholder):
collector, rc-gen, campaign-isolation, runner-drills, telemetry, all still
pass unchanged.

Declared the second real experiment,
`data/experiments/indefinite-transform-bugfix/predeclaration.json`:
hypothesis (the fix reduces `quit_stuck_rate` vs. the frozen phase1-500
baseline, 5.6%), primary outcome `quit_stuck_rate`, direction decrease,
minimum effect 2 points, alpha 0.05, 300 games/arm, seed_split validation,
arms `control` (`bugfix_indefinite_transform=false`) / `treatment`
(`bugfix_indefinite_transform=true`). 300 validation-split char_seeds from
a fresh pool (`4000000..4002999`, disjoint from both phase1-500's `0..499`
and lua-error-bugfix's `3000000..3002999`) via
`experiment.seeds_for_split`, written to
`data/experiments/indefinite-transform-bugfix/seeds.json`.

Committed and pushed the collected lua-error-bugfix results + the
indefinite-transform fix/tests/experiment scaffolding (`a96507d`) before
launching anything long-running, then separately archived the experiment's
arm-launch script into `ops/` (`a5f8efc`, same reasoning as the prior
session's `0c213f9`) before starting it.

**Started detached**: same hardened `setsid nohup ... & disown` form,
`ops/run-indefinite-transform-experiment.sh` (both arms sequentially,
300 games each via `--seeds-file`, `--turn-budget 20000 --wall-cap-secs 900
--workers 16`, run prefixes `exp-transform-control-`/
`exp-transform-treatment-`). Driver **PID 45766**, confirmed alive with 16
live `campaign.py` worker children for the control arm. Log:
`logs/indefinite-transform-experiment.log`. Per-arm summaries land at
`data/experiments/indefinite-transform-bugfix/{control,treatment}-summary.json`;
the script prints `EXPERIMENT_DONE` on completion.

**Result:** lua-error-bugfix experiment fully closed (measured, confirmed,
written up). Phase 2's second item (indefinite-transform stall root cause +
fix + config flag + regression test + predeclared experiment) is
code-complete and committed. The experiment measuring its actual effect is
running, not yet collected.

**Next step:** Check `ps -p 45766` / `tail logs/indefinite-transform-experiment.log`
/ existence of
`data/experiments/indefinite-transform-bugfix/treatment-summary.json`. Once
both summaries exist: `ops/collector.py --runs-dir data/runs --db
data/experiments/indefinite-transform-bugfix/results.db --strict`, then
compute each arm's `quit_stuck` count/n (`WHERE run_id LIKE
'exp-transform-control-%'` / `'exp-transform-treatment-%'`),
`experiment.evaluate_predeclaration`, write
`data/experiments/indefinite-transform-bugfix/result.json`. Sanity-check
first: control-arm `quit_stuck` rate should land near phase1-500's 5.6%
baseline (it's running the literal original stall); treatment should be
close to 0% (the fix should eliminate nearly all of it, since the baseline's
entire quit_stuck bucket was this one bug). Commit
`data/experiments/indefinite-transform-bugfix/{results.db,result.json,*-summary.json}`
once collected; if it clears its predeclared minimum effect, write the
result into `docs/decisions/012`'s Follow-up section (mirroring decision
011's). After that closes, PLAN §352-359's remaining Phase 2 candidates
(minimal spellcasting for casters — check pool share first; Felid
no-weapon plans; Mummy no-potion planning; Gnoll training skip; Djinn
HP-casting; Formicid escapes; Demigod goals; god-policy extensions) are
still open — but re-mining `data/phase1-500-report.json`'s stratified
tables the way this session found the Shapeshifter bug (by measured
failure rate, not by guessing off PLAN's example list) is probably a better
way to pick the next one than working PLAN's list in order.

## 2026-08-12 (session 3) — indefinite-transform-bugfix: control arm collected clean; treatment arm 100% contaminated, root-cause not pinned down, mitigated and relaunched

**Did:** Picked up the prior session's Next step: checked the
indefinite-transform-bugfix experiment (PID 45766, `setsid nohup ... &
disown`, launched last session). Control arm (300/300) finished healthy —
status mix (285 died, 8 quit_stuck, 3 lua_error, 3 timeout_wall) matched
organic variance, no uniform-signature red flags.

**Treatment arm came back 100% `harness_failure`** (300/300, every run
`"no 'Welcome,' banner within 60s (chargen stuck or crashed)"`,
`output_bytes=0`) — exactly the suspiciously-uniform pattern this project
has learned to distrust rather than average into a result (per the
relative-workdir pilot contamination precedent, `642e3ec`). Investigated
rather than accepted: ruled out the rc content/flag itself (manual replay
of the literal failing run.rc reached deep gameplay in ~3s), ruled out
`ProcessPoolExecutor`-at-16-workers-with-treatment-flavor as sufficient on
its own (a standalone post-hoc repro of the identical call path, same
worker count, same flag, run clean after the real experiment finished,
came back 14/16 died + 1 lua_error + 1 timeout_wall — zero
`harness_failure`), and ruled out generic host contention (idle CPU,
zero zombies, pty/fd counts trivial, identical des-cache footprint between
a healthy control run and a stuck treatment run; manual processes spawned
*while* the real pool was actively failing succeeded in ~3s every time,
which a genuinely exhausted shared resource wouldn't allow). Did **not**
find a single pinned-down root cause — full investigation log and the
one real (but insufficient-alone) contention data point in
`docs/decisions/013-treatment-arm-chained-launch-contamination.md`.

**Decision:** rather than continue open-ended forensics (diminishing
returns, per `CLAUDE.md`'s "adapt with the smallest working alternative...
do not stop to renegotiate"), discarded the contaminated treatment data
(300 run dirs moved to `/tmp/contaminated-exp-transform-treatment/`, not
committed; stale `treatment-summary.json` deleted) and relaunched the
treatment arm as its **own independent** `setsid nohup ... & disown`
process, decoupled from the control arm's wrapper script (the one
structural difference between every failing invocation and every
successful standalone reproduction), reusing the same `seeds.json` so the
paired-character design stays intact. Control arm's already-good data is
untouched and kept.

**Relaunched treatment arm standalone:**

    setsid nohup python3 ops/campaign.py \
      --seeds-file data/experiments/indefinite-transform-bugfix/seeds.json \
      --run-prefix exp-transform-treatment \
      --turn-budget 20000 --wall-cap-secs 900 --workers 16 \
      --runs-dir data/runs \
      --out data/experiments/indefinite-transform-bugfix/treatment-summary.json \
      > logs/indefinite-transform-treatment-retry.log 2>&1 < /dev/null &
    disown

**Result:** Control arm data good and preserved. Treatment arm redone from
scratch after contamination, cause not fully identified — flagged
explicitly in decision 013 for a future session if it recurs even fully
decoupled (would newly implicate `ProcessPoolExecutor`/`setsid`
interaction itself, worth an `strace`-level look at that point, not
before). No other Phase 2 work should be treated as blocked by this.

**Next step:** Check the retried treatment arm (`pgrep -fa
"exp-transform-treatment"` / `tail
logs/indefinite-transform-treatment-retry.log` /
`data/experiments/indefinite-transform-bugfix/treatment-summary.json`).
**Sanity-check before trusting it this time**, explicitly: status mix
should be organic-looking (mostly `died`, some `quit_stuck`, near-zero
`quit_stuck` if the fix works — control's quit_stuck rate was 8/300=2.67%
already lower than the phase1-500 baseline's 5.6%, curiously — worth a
second look once treatment's own numbers exist too), wall_secs/output_bytes
varied per run, and specifically **zero or near-zero `harness_failure`** —
if it comes back significantly non-zero `harness_failure` again, do not
retry a third time blind; escalate straight to the `strace`-level
investigation decision 013 flags, since two contaminated attempts back to
back would rule out "unlucky one-off." Once clean: `ops/collector.py
--runs-dir data/runs --db data/experiments/indefinite-transform-bugfix/results.db
--strict` (this will also reconcile the still-live `phase1-500`,
`lua-error-bugfix` run dirs already on disk — expect a large total count,
not just 600), compute each arm's `quit_stuck` count/n
(`run_id LIKE 'exp-transform-control-%'` / `'exp-transform-treatment-%'`),
`experiment.evaluate_predeclaration`, write `result.json`. Commit
`{results.db,result.json,control-summary.json,treatment-summary.json}` plus
decision 013 and this entry once collected. After that closes, resume
mining `data/phase1-500-report.json`'s stratified tables for the next
Phase 2 candidate (Troll/Felid lua_error clusters are likely already
explained by decision 011's two generic fixes rather than new bugs — worth
a quick check against decision 011's fix shape before assuming they need a
new investigation).
