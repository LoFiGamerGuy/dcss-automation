#!/usr/bin/env python3
"""Phase 2 exit criterion for docs/decisions/014: the qw upstream
spell-mana-affordability fix (plans-spells.lua's spell_castable() had
can_use_mp()'s sense inverted, blocking the cast exactly when affordable)
actually works, and the QW_BUGFIX_SPELL_MANA_CHECK rc flag actually toggles
it, against the real pinned + patched binary -- not a static read of the
patch.

Like decision 012's indefinite-transform fix, this isn't an exception to
provoke: the observable is a *decision* (is the spell castable right now),
so this drills the guard function directly
(qw_spell_uncastable_for_mana(sp, affordable)) through crawl's own
interactive Lua console (wizard mode `&`, then Ctrl-U -- see
bugfix-lua-errors-test.py's docstring for why the exact prompt-driven
choreography matters and why a blind-timed version misfires).
qw_spell_uncastable_for_mana() takes an explicit `affordable` override for
exactly this reason -- it can be driven by value (true/false) without
needing to actually be in either MP state in a real game, the same shape as
decision 012's qw_transform_is_indefinite(transform_name) taking an
explicit name override.

Usage: bugfix-spell-mana-test.py
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

DRILL_CHAR_SEED = 996
DRILL_GAME_SEED = 4997

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _materialize(run_id, workdir, bugfix_spell_mana_check):
    manifest, digest = combos.load_manifest()
    row = rc_gen.build_manifest_row(run_id, DRILL_CHAR_SEED, DRILL_GAME_SEED, manifest, digest)
    layout = rc_gen.write_run_dir(row, workdir, turn_budget=0,
                                   bugfix_spell_mana_check=bugfix_spell_mana_check)
    rc_path = layout["rc_path"]
    rc_path.write_text(rc_path.read_text().replace(": AUTO_START = true", ": AUTO_START = false"))
    cmd = [str(runner.CRAWL_BIN), "-rcdir", str(runner.QW_DIR), "-wizard"] + \
        [str(a) for a in layout["clo_args"]]
    return cmd, workdir


def _eval_console(cmd, workdir, lua_expr, timeout=30):
    """See bugfix-lua-errors-test.py's _eval_console -- identical
    choreography (must expect() each prompt's exact text rather than guess
    at timing; a blind second '&' hits a different wizard sub-command, not
    a reopened prompt)."""
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


def _run_case(bugfix_spell_mana_check, lua_expr, want_result):
    with tempfile.TemporaryDirectory(prefix="dcss-bugfix-spell-mana-drill-") as tmp:
        workdir = pathlib.Path(tmp)
        cmd, workdir = _materialize(
            f"drill-bugfix-spellmana-{'on' if bugfix_spell_mana_check else 'off'}",
            workdir, bugfix_spell_mana_check)
        text = _eval_console(cmd, workdir, lua_expr)

    needle = f"HARNESS_EVAL_RESULT: {want_result}"
    ok = needle in text
    detail = f"expected {needle!r} in output"
    if not ok:
        detail += f"; last 400 chars of output: {text[-400:]!r}"
    return ok, detail


def drill_fixed_affordable_is_castable():
    # Flag on, can afford the mana -> not blocked (false == "not
    # uncastable-for-mana", i.e. spell_castable proceeds to its other
    # checks). This is the exact case the original bug got backwards.
    return _run_case(True, 'qw_spell_uncastable_for_mana("Magic Dart", true)', "false")


def drill_fixed_unaffordable_is_blocked():
    return _run_case(True, 'qw_spell_uncastable_for_mana("Magic Dart", false)', "true")


def drill_unfixed_affordable_reproduces_bug():
    # Flag off -> reproduces the original inverted logic: affordable=true
    # is wrongly reported as uncastable-for-mana (blocked).
    return _run_case(False, 'qw_spell_uncastable_for_mana("Magic Dart", true)', "true")


def drill_unfixed_unaffordable_reproduces_bug():
    # Flag off -> affordable=false is wrongly reported as NOT
    # uncastable-for-mana (i.e. "castable" while unaffordable).
    return _run_case(False, 'qw_spell_uncastable_for_mana("Magic Dart", false)', "false")


DRILLS = [
    ("fixed: affordable -> not blocked", drill_fixed_affordable_is_castable),
    ("fixed: unaffordable -> blocked", drill_fixed_unaffordable_is_blocked),
    ("flag off: affordable -> reproduces original (wrongly blocked)",
     drill_unfixed_affordable_reproduces_bug),
    ("flag off: unaffordable -> reproduces original (wrongly not blocked)",
     drill_unfixed_unaffordable_reproduces_bug),
]


def main():
    if not runner.CRAWL_BIN.exists():
        print(f"bugfix-spell-mana-test.py: {runner.CRAWL_BIN} not found; build it first",
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
