#!/usr/bin/env python3
"""Phase 2 exit criterion for docs/decisions/011: the two qw upstream Lua
crash fixes (equipment.lua's `cur_equip` boolean-index, plans-rest.lua's
`hostile_servants_timer` nil-arithmetic) actually work, and the
QW_BUGFIX_LUA_ERRORS rc flag actually toggles them, against the real pinned
+ patched binary -- not a static read of the patch.

Both bugs only fire in specific in-game states (zero equipped items;
worshipping Makhleb) that aren't worth choreographing through real, timed
chargen/keypress sequences to reach reliably -- replay attempts against the
real phase1-500 campaign runs that hit these (docs/decisions/011) showed
qw's own play is not exactly reproducible run-to-run even at a fixed crawl
seed (likely un-seeded Lua-level tie-breaking inside qw itself), so a
gameplay-driven repro would be flaky by construction, not just slow.

Instead this drives crawl's own interactive Lua console (wizard mode `&`,
then Ctrl-U -- `debug_terp_dlua(clua)` in wizard.cc -- which evaluates code
in the *same* clua environment qw.lua and campaign.rc.tmpl already run in)
to call the two new guard functions directly by name:
`qw_hostile_servants_timer()` and `qw_equip_slot_or_empty(cur_equip, slot)`.
This exercises the real, live global environment (the real unassigned
`hostile_servants_timer` global; the real rc-settable
`QW_BUGFIX_LUA_ERRORS`), just not routed through the full should_rest()/
equip_letter_for_item() call chains -- which is the right scope for a
regression test of the fix itself.

Usage: bugfix-lua-errors-test.py
Exit 0 and prints "PASS" on success; exit 1 with the failure(s) on failure.
"""
import pathlib
import re
import sys
import tempfile
import time

import pexpect

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
import combos  # noqa: E402
import runner  # noqa: E402
import importlib.util

_spec = importlib.util.spec_from_file_location("rc_gen", str(ROOT / "ops/rc-gen.py"))
rc_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc_gen)

DRILL_CHAR_SEED = 998
DRILL_GAME_SEED = 4999

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _materialize(run_id, workdir, bugfix_lua_errors):
    manifest, digest = combos.load_manifest()
    row = rc_gen.build_manifest_row(run_id, DRILL_CHAR_SEED, DRILL_GAME_SEED, manifest, digest)
    layout = rc_gen.write_run_dir(row, workdir, turn_budget=0,
                                   bugfix_lua_errors=bugfix_lua_errors)
    # AUTO_START=true (campaign.rc.tmpl's default) would have qw driving its
    # own keys concurrently with the wizard-mode/console keys this test
    # sends -- noisy, not needed (this test doesn't touch real gameplay),
    # and the kind of macro-queue race docs/JOURNAL.md 2026-08-12 already
    # hit once for TURN_BUDGET's quit keys. Turn it off in the materialized
    # rc rather than duplicating campaign.rc.tmpl's QW_BUGFIX_LUA_ERRORS
    # substitution in a second template.
    rc_path = layout["rc_path"]
    rc_path.write_text(rc_path.read_text().replace(": AUTO_START = true", ": AUTO_START = false"))
    cmd = [str(runner.CRAWL_BIN), "-rcdir", str(runner.QW_DIR), "-wizard"] + \
        [str(a) for a in layout["clo_args"]]
    return cmd, workdir


def _eval_console(cmd, workdir, lua_expr, timeout=30):
    """Spawn crawl, enter wizard mode, open the dlua console (Ctrl-U), and
    evaluate lua_expr. Returns the ANSI-stripped captured text.

    Each step blocks on pexpect.expect() for the exact prompt text it's
    responding to, rather than a blind send-then-sleep -- '&' from normal
    gameplay only shows the "ABOUT TO ENTER WIZARD MODE" confirmation +
    "Enter Wizard Command" prompt the *first* time; a second '&' is itself a
    wizard sub-command (wizard.cc: case '&': wizard_list_companions()), not
    a way to reopen the prompt. Discovered by hand -- a blind-timed version
    of this reliably misfired onto "list companions" instead."""
    child = pexpect.spawn(" ".join(str(c) for c in cmd), timeout=timeout,
                           dimensions=(50, 130), cwd=str(workdir))
    buf = bytearray()
    try:
        child.expect(r"Welcome,", timeout=timeout)
        buf += child.before + child.after
        child.send("\r")
        child.send("&")
        child.expect(r"Do you really want to enter wizard mode\?", timeout=timeout)
        buf += child.before + child.after
        child.send("yes\r")
        child.expect(r"Enter Wizard Command", timeout=timeout)
        buf += child.before + child.after
        child.send("\x15")  # Ctrl-U: open the dlua console
        child.expect(r"Hit ESC to exit interpreter", timeout=timeout)
        buf += child.before + child.after
        # child.expect() on the marker text itself is unreliable here: the
        # console echoes the typed command line (including our own
        # HARNESS_EVAL_RESULT literal) back before Enter is even processed,
        # so a pattern match on the marker fires on the echo, not the real
        # output. The console is already known-open at this point (the
        # "Hit ESC to exit interpreter" expect above proved it), so a fixed
        # settle time for evaluation + a final drain is reliable here.
        child.send(f"crawl.mpr('HARNESS_EVAL_RESULT: ' .. tostring({lua_expr}))\r")
        time.sleep(1.5)
        try:
            while True:
                buf += child.read_nonblocking(size=65536, timeout=1)
        except (pexpect.TIMEOUT, pexpect.EOF):
            pass
        child.send("\x1b")  # ESC out of the interpreter
        try:
            while True:
                buf += child.read_nonblocking(size=65536, timeout=1)
        except (pexpect.TIMEOUT, pexpect.EOF):
            pass
    finally:
        try:
            if child.isalive():
                child.terminate(force=True)
                child.wait()
        except Exception:
            pass
    return ANSI_RE.sub("", bytes(buf).decode(errors="replace"))


# The upstream error class observed live against the real phase1-500
# campaign (docs/decisions/011): "attempt to perform arithmetic on ... a nil
# value". The original in-place expression (`hostile_servants_timer + 100`)
# named the global directly in its error text ("global
# 'hostile_servants_timer'"); routed through qw_hostile_servants_timer()'s
# return value here, Lua can no longer attribute a name to the nil (it's an
# anonymous call result, not a direct variable reference), so the message
# is the generic form -- same bug class, confirmed by the shared
# "arithmetic on ... nil value" phrasing, not the exact original string.
HOSTILE_TIMER_ERROR = "attempt to perform arithmetic on"
CUR_EQUIP_ERROR = "attempt to index"  # cur_equip local name varies by call site


def _run_case(bugfix_lua_errors, lua_expr, want_error_substr, want_result):
    with tempfile.TemporaryDirectory(prefix="dcss-bugfix-drill-") as tmp:
        workdir = pathlib.Path(tmp)
        cmd, workdir = _materialize(
            f"drill-bugfix-{'on' if bugfix_lua_errors else 'off'}", workdir, bugfix_lua_errors)
        text = _eval_console(cmd, workdir, lua_expr)

    if want_error_substr:
        ok = want_error_substr in text
        detail = f"expected error containing {want_error_substr!r}"
    else:
        needle = f"HARNESS_EVAL_RESULT: {want_result}"
        ok = needle in text
        detail = f"expected {needle!r} in output"
    if not ok:
        # Trim to the relevant tail for a useful failure message.
        detail += f"; last 400 chars of output: {text[-400:]!r}"
    return ok, detail


def drill_hostile_timer_fixed():
    # +100 matches the actual call-site expression in should_rest()
    # (plans-rest.lua) -- the crash is in the arithmetic at the call site,
    # not inside the helper itself (which, with the flag off, just returns
    # the possibly-nil raw global unchanged; tostring(nil) alone wouldn't
    # reproduce the bug, since tostring() never errors).
    return _run_case(True, "qw_hostile_servants_timer() + 100", None, "100")


def drill_hostile_timer_unfixed_reproduces_bug():
    return _run_case(False, "qw_hostile_servants_timer() + 100", HOSTILE_TIMER_ERROR, None)


def drill_cur_equip_fixed():
    return _run_case(True, 'qw_equip_slot_or_empty(false, "ring")', None, "false")


def drill_cur_equip_unfixed_reproduces_bug():
    return _run_case(False, 'qw_equip_slot_or_empty(false, "ring")', CUR_EQUIP_ERROR, None)


DRILLS = [
    ("hostile_timer: fixed (flag on) -> no crash, returns 0", drill_hostile_timer_fixed),
    ("hostile_timer: flag off -> reproduces original crash", drill_hostile_timer_unfixed_reproduces_bug),
    ("cur_equip: fixed (flag on) -> no crash, returns false", drill_cur_equip_fixed),
    ("cur_equip: flag off -> reproduces original crash", drill_cur_equip_unfixed_reproduces_bug),
]


def main():
    if not runner.CRAWL_BIN.exists():
        print(f"bugfix-lua-errors-test.py: {runner.CRAWL_BIN} not found; build it first",
              file=sys.stderr)
        sys.exit(1)

    failures = []
    for name, fn in DRILLS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"drill raised {type(e).__name__}: {e}"
        print(("ok  " if ok else "FAIL") + f" {name}: {detail}")
        if not ok:
            failures.append(f"{name}: {detail}")

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print(f"PASS: {len(DRILLS)}/{len(DRILLS)} bugfix drills confirmed against the real binary")
    sys.exit(0)


if __name__ == "__main__":
    main()
