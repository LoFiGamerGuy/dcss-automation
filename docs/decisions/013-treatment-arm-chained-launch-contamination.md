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

## Actual mitigation: chunk job submission to the worker count

`ops/campaign.py`'s `run_campaign()` now submits jobs to
`ProcessPoolExecutor` in sequential chunks of size `workers` (one full
pool lifecycle — construction, submission, drain, teardown — per chunk)
instead of handing the entire job list to a single pool at once. This is
the empirically-tested-safe shape (n=16 and n=48 both clean, repeatedly;
n=100 reliably broken) — not a diagnosed fix, a mitigation matched to what
was actually measured. Costs a small amount of per-chunk pool-startup
overhead (negligible next to per-game wall time) and preserves every
existing property (`--seeds-file` resumability, write-ahead accounting,
status reporting) unchanged. Re-ran `ops/campaign-test.py` after the
change: still passes (12/12 self-consistent, zero cross-contamination,
resume clean).

**If this recurs even with chunking** (i.e. a single 16-job chunk starts
failing), that would newly implicate something at the worker-count level
itself rather than backlog size, and is worth the deeper kernel-level
investigation (`strace -f` across the whole pool from the moment of
`fork`/`exec`, or comparing `/proc/<pid>/status` `SigBlk`/`SigCgt` masks
between a healthy and a stuck run) that this session didn't have budget
left for.
