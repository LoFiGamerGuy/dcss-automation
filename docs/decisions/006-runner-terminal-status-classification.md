# 006 — Runner terminal-status classification

**Context.** PLAN.md §6 defines ten terminal statuses for a run: `won |
died | quit_intentional | quit_stuck | lua_error | crashed | timeout_turns |
timeout_wall | invalid_telemetry | harness_failure`. Building `ops/runner.py`
required pinning down, against the actual pinned crawl+qw source (not
guessed), what observable signal maps to each one.

**Logfile row is authoritative for natural ends.** crawl's own end-of-game
xlog row ("logfile", distinct from the DGL_MILESTONES "milestones" file)
lands at `<-dir>/saves/logfile-seeded` (the extra nested `saves/` and the
`-seeded` qualifier are both real, confirmed against `hiscores.cc` /
`state.cc` / `initfile.cc` and empirically). It's written synchronously
(`hiscores.cc`'s `logfile_new_entry`: fopen "a" / write / fclose) the moment
the game ends, before any post-game UI screens, so polling for its
appearance is race-free and doesn't require shepherding the process through
"-more-"/dump screens to reach process EOF.

Its `ktyp=` field (kill-method-type.h / hiscores.cc's kill_method_names[])
maps as:
- `winning` → **won**
- `quitting` (Ctrl-Q + "yes") → **quit_stuck**, not quit_intentional. Read
  through qw.lua: the only place it ever sets `goal_status = "Quit"` is its
  own `QUIT_TURNS`-driven stuck-detection (`determine_goal()`, ~line 4190)
  plus one low-HP edge case that folds into the same branch — there is no
  other self-initiated quit path in qw. So every `ktyp=quitting` row this
  system will ever produce *is* qw's stuck-quit.
- `leaving` (walked out the D:1 stairs without the Orb) → **quit_intentional**.
  This is qw's own `goal_status == "Escape"` machinery choosing to bail —
  a deliberate, not-stuck decision, which is exactly what
  `quit_intentional` should mean. Confirmed via `stairs.cc:852-853`:
  `ouch(INSTANT_DEATH, player_has_orb() ? KILLED_BY_WINNING :
  KILLED_BY_LEAVING)`.
- anything else → **died**. There is no single generic "died" ktyp value —
  it's whichever real cause fired (`mon`, `pois`, `starvation`, ...).

**No row means the process never reached `ouch()`'s terminal branch** —
confirmed by reading the call chain (`ouch()` → `end_game()` → `end.cc:291-292`
→ `logfile_new_entry()`), which only runs from that one path. A signal-killed
process (real crash or an external `kill -9`) never gets there, so "no row"
splits by *how* the process ended:
- terminated by a signal we didn't send (`child.signalstatus` set, and we
  didn't call `_kill()` first) → **crashed**. This deliberately covers both
  a real segfault and an external `kill -9` under the same bucket — from
  the harness's perspective both are "died via a signal we didn't issue,
  with no valid terminal row", which is what `crashed` means here. Verified
  directly by the kill-9 drill in `ops/runner-drills-test.py`.
- otherwise, a Lua error banner in the captured pty text (`Lua error|LUA
  ERROR|traceback`) → **lua_error**. A clua-caught Lua error is non-fatal
  to the crawl process itself (crawl's error handler prints via `mprf`, it
  doesn't crash) — it usually leaves qw broken and the game effectively
  stuck rather than reaching a clean EOF, which is why the error-pattern
  check runs *before* concluding hang or wall-cap, not only at EOF (see
  below).
- otherwise → **invalid_telemetry**: the process ended and we have neither
  a row nor an identifiable cause.

**`timeout_turns` is deliberately not enforced from inside clua.** clua has
no io/os library (`clua.cc`: `LUA_IOLIBNAME`/`LUA_OSLIBNAME` are commented
out of the loaded lib list), so a marker *file* from inside the game isn't
possible — `campaign.rc.tmpl`'s harness hook wraps qw's own `ready()` and
only *prints* an on-screen sentinel (`HARNESS_TIMEOUT_TURNS`) once
`you.turns()` crosses the budget.

An earlier version also tried sending the Ctrl-Q "yes" quit sequence from
that same Lua hook (`crawl.process_keys`, the same primitive qw's own
`plan_quit()` uses). It hung: those keys get queued into the same
in-process macro buffer qw's own `ready()` is concurrently feeding
movement/action keys into every tick, and the two interleaved
unpredictably — confirmed by hand twice, once producing a process that
just sat alive indefinitely after the sentinel fired, once producing an
unrelated qw Lua error later in the same run (`attempt to index local
'cur_equip' (a boolean value)`) after the quit attempt evidently got
absorbed as normal input instead of reaching the confirmation prompt.

The fix: the Lua hook *only* observes and announces; `ops/runner.py`
watches the pty stream for the sentinel from the outside and kills the
process itself the moment it's seen. This is the same external channel a
human (or qw's own `util/qw.exp`) types into, so it can't race qw's
internal queueing — and since a killed process never writes a logfile row,
there's no classification ambiguity to resolve either: sentinel-seen means
`timeout_turns`, full stop, regardless of what might have happened to the
game state a tick later had we not killed it.

**Hang detection reuses `ops/run-canary.py`'s established fix** (checking
error patterns before concluding hang — a crashed-and-frozen game looks
identical to a genuinely stuck one from the outside; see the 2026-08-12
journal entry for the original bug). On a real hang, `runner.py` attempts
one graceful save first (Ctrl-S, PLAN §6), which surfaced a second real
bug while writing the hang drill: `save_game(true)` (`files.cc:2603`,
`leave_game=true`) *exits the process after saving* — a plain save does
not touch the logfile (only `ouch()`/`end_game()` does), so a naive
"EOF with no row" check after the save misrouted a successful hang-drill
save into `invalid_telemetry`. Fixed by having the EOF branch check
whether the grace-save was already attempted and, if so, classify as
`timeout_wall` directly rather than falling through to the generic
no-row-EOF path.

**Verification.** `ops/runner-drills-test.py` runs all three PLAN §9
forced-failure drills (induced Lua error, kill -9, hang) against the real
pinned binary, not a mocked classifier — 3/3 pass. `timeout_turns` was also
verified manually (not one of the three named drills, but a status this
system introduces itself): a `--turn-budget 5` run reliably classifies
`timeout_turns` in ~2s.
