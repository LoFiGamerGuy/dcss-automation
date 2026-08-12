# 016 — Root cause of the "intermittent" treatment-arm chargen freeze: crawl caps -name at 30 chars, and the treatment prefix produced 31-char names

Supersedes the open root-cause question in
[013-treatment-arm-chained-launch-contamination.md](013-treatment-arm-chained-launch-contamination.md).
Found during the 2026-08-12 orchestrator review (third pass).

## Root cause

`run_id` is passed to crawl verbatim as `-name`. Crawl hard-caps player
names at `MAX_NAME_LENGTH = 30` (`externs.h:81`); `is_good_name()`
(`ng-input.cc:84`) rejects anything longer. An overlong `-name` from the
command line is **silently** invalid: crawl parks at its native startup
menu (the "Dungeon Crawl / Choose Game Seed / Tutorial / ..." screen
decision 013's `logfile_read` capture found), the name field never
auto-fills, and Enter is consumed without producing any output because the
menu refuses to start a game with an invalid name (`startup.cc:877`'s
input loop only appends printable chars while under the cap; the start
action re-validates). To the harness this is exactly "no 'Welcome,' banner
within 60s" with a keystroke that is delivered (`rchar` advances) but does
nothing — decision 013's precise, previously unexplained observation.

Arm run_ids are `<prefix>-<7-digit char_seed>`, i.e. `len(prefix) + 8`:

| prefix | name length | outcome |
|---|---|---|
| `exp-transform-control` | 29 | 300/300 clean |
| `exp-transform-treatment` | **31** | 100% harness_failure, every launch |
| `exp-luafix-control` / `-treatment` | 26 / 28 | both arms clean |
| `phase1-500` | 17 | clean |
| `exp-spellmana-control` | 29 | (would have passed) |
| `exp-spellmana-treatment` | **31** | (would have failed identically) |

## Why five sessions read this as an intermittent race

Every launch that used the real treatment prefix failed 100%: the original
chained script, the standalone `setsid` relaunch, the chunked full-300 run,
the post-`runs_dir.resolve()` relaunch, every retry-wrapper attempt (4+),
and this review's 16-seed slice. Every diagnostic that "reproduced the same
thing cleanly" used a shorter scratch prefix (or a hand-chosen name in the
manual replays): n=8/16/48/128 probes, `campaign-test.py` (12 games), the
wizard-mode drills. The apparent correlates 013 chased — job-list size,
chunking, fork-vs-spawn, relative-vs-absolute paths, chained-vs-standalone
launch — were all artifacts of which prefix each particular test happened
to use. The failure was never intermittent; it was a deterministic function
of one variable nobody listed as a variable.

Decisive minimal pair (this review, same seed 4000004, same flavor, same
`data/runs`, same machine state, one character of prefix difference):

- `exp-transform-treatment-4000004` (31 chars): harness_failure, ~65s,
  welcome timeout — reproduced twice (n=16 slice, then n=1).
- `exp-transform-treatmen-4000004` (30 chars): `died` normally in 8.9s.

Cross-checks: an 8-seed control-flavor batch in `data/runs` (25-char
names) and an 8-seed treatment-flavor batch in `/tmp` (27-char names) both
came back with organic status mixes, eliminating the bugfix flag and the
runs-directory as factors under the current machine state.

This also retro-explains the most misleading coincidence in the project so
far: the control/treatment prefix pair differed in name length *exactly*
across the 30-char boundary, so the failure tracked the
`bugfix_indefinite_transform` flag perfectly without having anything to do
with it — and the queued caster-spell-mana experiment's prefix pair
(29/31) would have reproduced the same flag-correlated illusion.

## Fixes applied

1. `ops/rc-gen.py` `build_manifest_row()` now raises `ValueError` on any
   `run_id` longer than 30 chars — fail fast at write-ahead time, never
   silently hang at chargen.
2. Treatment arm relaunched under prefix `exp-transform-treat` (27-char
   names), same `seeds.json` (paired design intact). Collector queries for
   this arm must use `run_id LIKE 'exp-transform-treat-%'`.
3. `ops/run-caster-spell-mana-experiment.sh` treatment prefix shortened to
   `exp-spellmana-treat` before that experiment ever runs.
4. `ops/run-indefinite-transform-treatment-with-retry.sh` is superseded:
   purge-and-retry could never have worked (the failure is deterministic,
   not a race). Kept for history with a header note.
5. All poisoned treatment-arm data purged before relaunch: 240
   welcome-timeout `harness_failure` results across attempts, 16 more from
   this review's slice test, 16 manifest-only dirs from the killed wrapper,
   and 12 `spawn failed` results left over from the session-5 rebuild
   collision (which the purge script deliberately didn't match — they were
   being silently skipped by resume and would have shipped as garbage
   inside the final arm; see the journal's orchestrator entry).

## Lesson recorded

When an A/B experiment's two arms differ in *any* incidental way besides
the treatment variable — even the length of their run-ID strings — a
harness-level failure can masquerade as a treatment effect. The rc-gen
guard closes this instance; the general rule is that arm prefixes should be
chosen to be structurally identical (same length, same charset) from now
on.
