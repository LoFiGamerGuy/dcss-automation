# 013 — indefinite-transform-bugfix treatment arm: 100% harness_failure, not root-caused, mitigated by chunking job submission

**Update after further investigation (same day):** the "decouple arm
launches" mitigation below was tried and **did not work** — a fully
independent standalone `setsid` relaunch of the treatment arm reproduced
the identical 100% `harness_failure` a second time. Real root cause
investigation continued past this file's original text; see "Further
investigation" and "Actual mitigation" sections below the original
write-up, which is kept for the historical record of what was ruled out.

## Symptom

`ops/run-indefinite-transform-experiment.sh` (control then treatment,
sequentially, both inside one `setsid nohup ... & disown` process) produced
a clean control arm (300/300, organic status mix matching the phase1-500
baseline shape) immediately followed by a **100% `harness_failure`**
treatment arm (300/300, every single run `"no 'Welcome,' banner within 60s
(chargen stuck or crashed)"`, `output_bytes=0`). This is exactly the kind of
suspiciously-uniform signature this project has learned to distrust (see
decision-adjacent journal entry on the relative-workdir pilot contamination,
commit `642e3ec`) rather than accept as organic variance — investigated
before considering the data usable.

## Investigation (each candidate tested directly, not assumed)

1. **rc content / the flag itself.** Diffed a real contaminated treatment
   run's `run.rc` against a healthy control run's `run.rc` from the same
   experiment — only difference is `QW_BUGFIX_INDEFINITE_TRANSFORM = true`
   vs `= false` (and the sampled combo). Manually replayed the *exact*
   contaminated run's `run.rc` with the correct full CLO set (including
   `-rcdir vendor/qw`, which a first manual attempt omitted and which
   produced a red herring "Cannot find file qw.rc" error not seen in the
   real failures) as a single foreground process: reached deep gameplay in
   ~3s. Ruled out.
2. **Concurrency count / ProcessPoolExecutor itself.** Reproduced
   `runner.run_game()` calls through a real `ProcessPoolExecutor`
   (matching `campaign.py`'s exact code path, not just raw `pexpect`) at
   4 workers (pure treatment flavor) and 16 workers (pure treatment
   flavor, matching the real experiment's worker count) as **standalone**
   invocations, run *after* the real experiment had already finished: both
   completed cleanly (14/16 died normally, 1 lua_error, 1 timeout_wall —
   a completely ordinary status mix, zero `harness_failure`). Ruled out
   "16 concurrent treatment-flavor workers" as sufficient to reproduce on
   its own.
3. **Host contention.** `vmstat` during the failure window showed the
   system 91-100% idle; the 16 stuck crawl processes were in
   `poll_schedule_timeout`/`wait_woken` (genuinely blocked waiting for
   pty I/O, not spinning); no zombies; pty count 18/4096; open fd count
   trivial; no semaphore/shm leaks; `data/runs/` directory size (1620
   entries, 23GB) identical between a healthy control run and a stuck
   treatment run's des-cache footprint (13MB / 545 files each, matching).
   Manually spawning fresh processes (both single and 8-way
   `ThreadPoolExecutor`-concurrent) *while the real 16-worker treatment
   pool was still actively failing* succeeded in ~3s every time — disproves
   generic system-wide resource exhaustion, since a genuinely exhausted
   resource would have blocked these too.
4. **One data point did fail under load:** an 8-job *mixed* (4
   treatment-flavor + 4 control-flavor) `ProcessPoolExecutor` test, run
   concurrently with the real 16-worker treatment pool (~24 total crawl
   processes, at the CPU core count), hung and was killed by the tool's own
   120s timeout. This is suggestive of true oversubscription mattering at
   the margin, but it doesn't explain the real failure: the real 16-worker
   pool's *own* first 16 tasks were already 100% `harness_failure` before
   any of this diagnostic load existed, when total system load was just
   its own 16 processes — the same count control used successfully minutes
   earlier.

## Root cause: not fully identified

No single reproducible root cause was isolated. The strongest remaining
candidate, by elimination, is something specific to launching the
treatment arm as the **second `python3 ops/campaign.py` invocation inside
a single already-`setsid`-detached wrapper script**, immediately following
a 300-game `ProcessPoolExecutor` pool's full teardown in the same parent
shell process — as opposed to a fresh, independent `setsid nohup ... &
disown` invocation per arm (which is exactly how every standalone
reproduction attempt above was launched, and which never once failed).
This project has already found `setsid`/session-boundary interactions to
be a real, non-obvious source of process-detachment bugs here (the pilot
that died with zero output until `setsid` was added) — plausible this is
a second instance of the same general class, not yet pinned down to a
specific syscall or resource.

## Decision: decouple arm launches, don't chase further synchronously

Per `CLAUDE.md` ("adapt with the smallest working alternative... do not
stop to renegotiate" / diagnose-then-move-on rather than open-ended
forensics): discarded the contaminated 300-run treatment arm (moved aside
to `/tmp/contaminated-exp-transform-treatment/`, not committed, not part
of any data set), deleted the stale `treatment-summary.json`, and
**relaunch the treatment arm as its own independent `setsid nohup ... &
disown` process**, decoupled from the control arm's script, using the
same `seeds.json` (paired-character design must stay intact) so it's
still directly comparable to the already-good control-arm data. If this
recurs even when fully decoupled, that would newly implicate the
`ProcessPoolExecutor`/`setsid` interaction itself rather than
script-chaining, and would be worth a deeper `strace`-level investigation
at that point — not before, since two clean explanations (decoupling, or
genuine but rare transient contention) are cheaper to falsify by simply
re-running than to keep forensically chasing blind.

**For future sessions:** launch every experiment arm as its own
top-level `setsid nohup python3 ops/campaign.py ... & disown` command,
never chained sequentially behind another arm inside one wrapper script,
even though this project's existing wrapper-script pattern (see
`ops/run-lua-error-experiment.sh`) did *not* exhibit this problem for the
lua-error-bugfix experiment — that one may simply have gotten lucky, or
there is a real difference not yet identified. Treat any future 100%
(or near-100%) `harness_failure`/uniform-timing batch the same way this
one was: stop, diagnose before trusting, don't average it into a result.

## Further investigation: decoupling did not work; the real correlate is job-list size

The standalone-relaunch mitigation above was applied and immediately
re-tested. It reproduced the identical 100% `harness_failure` signature —
disproving "chained after control" as the cause. Continued rather than
accept a second unexplained loss:

- Attached `strace -p` (via passwordless `sudo`, `ptrace` isn't permitted
  unprivileged in this sandbox) to a live stuck worker: it was blocked in
  `read(0, ...)` — i.e. **the crawl child had already rendered past
  "Welcome," and was waiting for a keypress**, not hung computing anything.
  This flips the earlier framing: the game itself is fine; the harness's
  own `pexpect.expect(r"Welcome,")` in the monitoring worker process never
  saw/matched output the child had genuinely already produced, so it never
  sent the follow-up `\r` and the child sat waiting forever until the 60s
  timeout killed it.
- Systematically bisected the one remaining uncontrolled variable, job-list
  size, via direct `runner.run_game()` calls through a real
  `ProcessPoolExecutor` (matching `campaign.py`'s exact code path):
  - n=8 (mixed control+treatment flavor, concurrent with the real failing
    pool), n=16 (pure treatment, both via a direct script and via
    `campaign.py`'s actual CLI with the real seeds), n=16 twice more
    under an explicit `setsid` launch (isolating that variable too): **all
    succeeded cleanly, repeatedly** (>10 trials total).
  - n=100 (real CLI, real seeds subset, `setsid`-launched): **0/100
    completions after 150s+**, same `read(0)`-blocked signature via
    `strace`. Reproduced with the platform-default `fork` start method.
  - Suspected a classic `fork()`-with-active-threads hazard
    (`ProcessPoolExecutor`'s call-queue feeder thread busy exactly when a
    worker forks, child inherits a lock nobody in the child will ever
    release) since a large pending backlog is exactly the condition that
    maximizes that race's odds. Tested the standard fix —
    `mp_context=multiprocessing.get_context("spawn")`, which avoids
    inheriting any parent thread state — at the same n=100 scale: **still
    0/100, identical signature.** This rules the fork/thread-race theory
    out; whatever the mechanism is, it is not specific to `fork`.
  - n=48 (real CLI, real seeds, chunked into 3 sequential batches of 16 —
    see mitigation below): **48/48 clean, zero `harness_failure`.**

No further mechanism was identified within the `ProcessPoolExecutor`/
`pexpect`/pty stack to explain why job-list size specifically (not worker
count, not `fork` vs `spawn`, not `setsid`, not real vs. synthetic seeds)
determines whether the monitoring process's `pexpect.expect()` reliably
observes output its own child already produced. This remains open for a
future session with more `strace`/kernel-level budget than was spent here.

## Actual mitigation, part 1: chunk job submission to the worker count

`ops/campaign.py`'s `run_campaign()` now submits jobs to
`ProcessPoolExecutor` in sequential chunks of size `workers` (one full
pool lifecycle — construction, submission, drain, teardown — per chunk)
instead of handing the entire job list to a single pool at once. Cheap,
harmless, kept as defense in depth even after part 2 below pinned down
the real fix — costs only a small amount of per-chunk pool-startup
overhead. Re-ran `ops/campaign-test.py` after the change: still passes
(12/12 self-consistent, zero cross-contamination, resume clean).

## Real fix, part 2: `run_campaign()` never resolved its own `runs_dir` to absolute

Chunking alone did **not** fix it — a chunked, full 300-job real run
(`--runs-dir data/runs`, the relative form every prior launch command in
this project has used) still came back 100% `harness_failure` on its very
first chunk. Bisected the one remaining variable systematically:

- A hand-written script calling the real `runner.run_game()` directly
  (bypassing `campaign.py`'s `run_campaign()` entirely) with an
  **absolute** `workdir` built from `pathlib.Path(".").resolve()`
  succeeded cleanly at every scale tried (n=8, 16, 48, 100).
- Calling `campaign.run_campaign()` — the actual function, imported from
  the real module, not reimplemented — with the same real 300-seed list
  and `runs_dir="data/runs"` (**relative**, matching every real launch
  command used all day) reproduced the 100% failure on its first chunk of
  16, even after the chunking fix from part 1.
- Calling `campaign.run_campaign()` again, identical in every other way,
  with `runs_dir=str(ROOT / "data/runs")` (**absolute**): clean —
  128/128 across 8 chunks with zero `harness_failure`, in a dedicated
  confirmation run after the first 48/48 success.

This is despite `rc_gen.write_run_dir()` and `runner.run_game()` **both**
already resolving their own `workdir` parameter to absolute internally
(the fix for the original relative-workdir pilot contamination,
`642e3ec`) — evidently insufficient on its own, since the relative
`runs_dir` still causes real breakage somewhere upstream of those
resolve() calls that wasn't identified at the syscall level (a
`strace -f` comparison between a healthy and a stuck run, from the moment
of `fork()`, would be the next step if this resurfaces — not pursued here
given the fix was already confirmed working).

**This also explains why `bugfix_indefinite_transform=True` looked like
part of the puzzle** even though its own code cannot execute before
"Welcome," appears: every previously-successful full-scale campaign in
this project (phase1-500, the lua-error-bugfix experiment, and this same
experiment's own control arm) happened to also use a relative
`--runs-dir data/runs` and never hit this — but none of them had
`bugfix_indefinite_transform=True` either, so the relative-path bug and
the flag were confounded in the data available until this session
isolated them independently.

**Fix applied:** `run_campaign()` now does
`runs_dir = pathlib.Path(runs_dir).resolve()` immediately, before
`runs_dir` is ever used to build a single `workdir`. Every `--runs-dir`
argument, relative or absolute, now behaves identically. Re-ran
`ops/campaign-test.py` and `ops/rc-gen-test.py` after this change: both
still pass. Kept as a real, independently-justified fix (matches this
codebase's own established convention) even though, see below, it turned
out not to be the actual explanation for the treatment arm's failures.

## The absolute-path fix did not actually hold up; final characterization and mitigation

A relaunch of the real treatment arm *with the `runs_dir.resolve()` fix
applied* failed 100% again, identically (`strace` on a live stuck process
confirmed it was blocked in `read(0, ...)` with absolute, correctly
resolved `-rc`/`-dir` paths — the fix from part 2 above was genuinely in
effect, and it didn't matter). The earlier 128/128-clean confirmation run
was real but was not actually caused by the absolute-path change — it was
one lucky trial among several, not a deterministic fix. This is the
clearest evidence yet that **the underlying failure is a genuine
intermittent race**, not deterministically tied to any single code-level
variable tested today (job-list size, chunking, `fork` vs `spawn`,
relative vs. absolute paths, `setsid`, real vs. synthetic seeds) — full
300-scale real attempts have both succeeded and failed 100% with *no
code difference between some pairs of them*.

**What the freeze actually looks like, pinned down via a `pexpect`
`logfile_read` capture on a live stuck worker:** the crawl process is not
stuck computing and not stuck at the "Welcome," chargen banner — it's
frozen at crawl's own native pre-chargen "choose game type" menu
("Dungeon Crawl" / "Choose Game Seed" / "Tutorial" / "Hints Mode" / ...,
with "Dungeon Crawl" pre-highlighted), a screen `AUTO_START`/`combo=`
normally causes crawl to skip past without ever displaying. Tried the
obvious fix — have `monitor_game()` send `"\r"` periodically while
waiting for "Welcome," instead of only after matching it, to dismiss this
menu if it appears — and confirmed via `/proc/<pid>/io` that the
keystroke *was* delivered (`rchar`/`syscr` advanced by exactly one read)
but produced **zero** new output (`wchar` stayed frozen): the process
received the input and did nothing observable with it. This rules out
"missing dismiss keystroke" as the actual mechanism too, and was reverted
(no behavior change, just noise) rather than kept as a non-fix.

**Decision: stop chasing root cause, mitigate with retry.** This
project's guidance is explicit about not spending unbounded time once
returns diminish (`CLAUDE.md`: "adapt with the smallest working
alternative... do not stop to renegotiate"), and today's investigation —
extensive, systematic, each hypothesis directly tested rather than
guessed — has not converged on one. Since the failure is confirmed
intermittent and not tied to any specific character/seed (both arms
share seeds; the control arm, with `bugfix_indefinite_transform=False`,
has never once shown this signature; several full treatment-flavor
runs succeeded cleanly), **retrying a purged failure is a legitimate
mitigation**, not a data-integrity risk: a character that hit a
startup-time race once has no special reason to hit it again, and the
purge is narrowly scoped to the exact `"no 'Welcome,' banner within Ns"`
detail string — a real crash-with-no-row `harness_failure` is left
alone and still counts.

Built `ops/purge-welcome-timeout-failures.py` (deletes only run
directories whose `result.json` is that specific detail string,
verified against synthetic fixtures: a real `died` and a different
`harness_failure` detail are both left untouched) and
`ops/run-indefinite-transform-treatment-with-retry.sh` (loops
`campaign.py` + the purge script up to 6 attempts, relying entirely on
`campaign.py`'s existing resume-by-`run_id` logic to retry exactly the
purged runs and nothing else). This is the launch mechanism used to
finally collect this experiment's treatment arm.

**If a future campaign hits this same signature:** don't re-derive the
above from scratch — use the same purge-and-retry mechanism directly.
If retries start being needed pervasively (not just for this one
experiment) it would be worth generalizing
`run-indefinite-transform-treatment-with-retry.sh`'s loop into
`campaign.py` itself (a `--retry-welcome-timeouts N` flag) rather than
copy-pasting the wrapper shape per experiment.
