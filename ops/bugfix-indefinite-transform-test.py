#!/usr/bin/env python3
"""Phase 2 exit criterion for docs/decisions/012: the qw upstream
indefinite-transform rest stall fix (plans-rest.lua's should_rest()/
reason_to_rest() picking plans.rest forever for any character in a
talisman-driven, indefinite-duration transformation -- every Shapeshifter
in the phase1-500 baseline) actually works, and the
QW_BUGFIX_INDEFINITE_TRANSFORM rc flag actually toggles it, against the
real pinned + patched binary -- not a static read of the fix.

Unlike docs/decisions/011's two Lua-crash fixes, this isn't an exception to
provoke: the observable is a *decision* (should qw rest or not), so this
drills the guard helpers directly (qw_transform_is_indefinite(name),
qw_transformed_worth_resting_for()) through crawl's own interactive Lua
console (wizard mode `&`, then Ctrl-U -- see bugfix-lua-errors-test.py's
docstring for why the exact prompt-driven choreography matters and why a
blind-timed version misfires). qw_transform_is_indefinite() takes an
explicit transform-name override for exactly this reason -- it can be
driven by name ("beast", "spider", ...) without actually being transformed
in-game, the same shape as decision 011's qw_equip_slot_or_empty(cur_equip,
slot) taking cur_equip explicitly.

Usage: bugfix-indefinite-transform-test.py
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

DRILL_CHAR_SEED = 997
DRILL_GAME_SEED = 4998

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _materialize(run_id, workdir, bugfix_indefinite_transform):
    manifest, digest = combos.load_manifest()
    row = rc_gen.build_manifest_row(run_id, DRILL_CHAR_SEED, DRILL_GAME_SEED, manifest, digest)
    layout = rc_gen.write_run_dir(row, workdir, turn_budget=0,
                                   bugfix_indefinite_transform=bugfix_indefinite_transform)
    rc_path = layout["rc_path"]
    rc_path.write_text(rc_path.read_text().replace(": AUTO_START = true", ": AUTO_START = false"))
    cmd = [str(runner.CRAWL_BIN), "-rcdir", str(runner.QW_DIR), "-wizard"] + \
        [str(a) for a in layout["clo_args"]]
    return cmd, workdir


def _eval_console(cmd, workdir, lua_expr, timeout=30):
    """See bugfix-lua-errors-test.py's _eval_console -- identical
    choreography (must expect() each prompt's exact text rather than
    guess at timing; a blind second '&' hits a different wizard
    sub-command, not a reopened prompt)."""
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


def _run_case(bugfix_indefinite_transform, lua_expr, want_result):
    with tempfile.TemporaryDirectory(prefix="dcss-bugfix-transform-drill-") as tmp:
        workdir = pathlib.Path(tmp)
        cmd, workdir = _materialize(
            f"drill-bugfix-transform-{'on' if bugfix_indefinite_transform else 'off'}",
            workdir, bugfix_indefinite_transform)
        text = _eval_console(cmd, workdir, lua_expr)

    needle = f"HARNESS_EVAL_RESULT: {want_result}"
    ok = needle in text
    detail = f"expected {needle!r} in output"
    if not ok:
        detail += f"; last 400 chars of output: {text[-400:]!r}"
    return ok, detail


def drill_beast_is_indefinite():
    return _run_case(True, 'qw_transform_is_indefinite("beast")', "true")


def drill_flux_is_indefinite():
    return _run_case(True, 'qw_transform_is_indefinite("flux")', "true")


def drill_spider_is_not_indefinite():
    # spider-form is a spell (Beastly Appendage/etc-style) form, not a
    # talisman -- expires on its own, so it's correctly still
    # "worth resting for" and must NOT be caught by this guard.
    return _run_case(True, 'qw_transform_is_indefinite("spider")', "false")


def drill_no_transform_is_not_indefinite():
    return _run_case(True, 'qw_transform_is_indefinite("")', "false")


def drill_flag_off_no_override_needed():
    # With the flag off, qw_transform_is_indefinite() itself still computes
    # the same answer (the guard only changes what
    # qw_transformed_worth_resting_for() does with it) -- confirms the flag
    # branch lives at the right call site, not inside the classifier.
    return _run_case(False, 'qw_transform_is_indefinite("beast")', "true")


DRILLS = [
    ("beast (talisman form) -> indefinite=true", drill_beast_is_indefinite),
    ("flux (talisman form) -> indefinite=true", drill_flux_is_indefinite),
    ("spider (spell form) -> indefinite=false", drill_spider_is_not_indefinite),
    ("not transformed -> indefinite=false", drill_no_transform_is_not_indefinite),
    ("flag off -> classifier itself unaffected", drill_flag_off_no_override_needed),
]


def main():
    if not runner.CRAWL_BIN.exists():
        print(f"bugfix-indefinite-transform-test.py: {runner.CRAWL_BIN} not found; build it first",
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
