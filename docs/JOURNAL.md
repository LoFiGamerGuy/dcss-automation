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

**Next step:** Build the campaign driver: a `ops/campaign.py` (or similar)
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
