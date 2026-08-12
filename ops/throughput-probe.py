#!/usr/bin/env python3
"""Phase 0 throughput measurement (PLAN.md §5/§9): run a sample of legal
combos to natural completion (death/win/stuck), each wrapped in `/usr/bin/time
-v` for wall-clock/CPU/peak-RSS, and write a JSON report. This also doubles
as a rune-milestone probe (docs/decisions/005) — reaching a rune requires
real depth that a short interactive test budget can't reach, so games here
run with only a generous safety cap, not the short budgets ops/run-canary.py
and ops/telemetry-test.py use.

This is deliberately not the real Phase 1 runner (turn-budget based state
machine, write-ahead accounting) — it's the minimal driver Phase 0 needs to
produce a throughput number before that gets built. Games are capped by
wall-clock here (not turns) specifically *because* this is measuring
wall-clock, not because that's the intended long-term policy — see
PLAN.md §6 on why turn budgets are used everywhere else.

Usage: throughput-probe.py [--n-games N] [--safety-cap-secs N] [--workers N]
                            [--out PATH]
"""
import argparse
import json
import pathlib
import random
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parent.parent
CRAWL_BIN = ROOT / "vendor/crawl/crawl-ref/source/crawl"
QW_DIR = ROOT / "vendor/qw"
RC_TMPL = ROOT / "ops/canary/canary.rc.tmpl"
MANIFEST = ROOT / "data/manifests/legal-characters.json"

TIME_RE = {
    "wall_secs": re.compile(r"Elapsed \(wall clock\) time.*?: (?:(\d+):)?(\d+):(\d+(?:\.\d+)?)"),
    "user_secs": re.compile(r"User time \(seconds\): (\d+\.\d+)"),
    "sys_secs": re.compile(r"System time \(seconds\): (\d+\.\d+)"),
    "max_rss_kb": re.compile(r"Maximum resident set size \(kbytes\): (\d+)"),
}


def sample_combos(n, seed):
    manifest = json.loads(MANIFEST.read_text())
    combos = manifest["combos"]
    rng = random.Random(seed)
    if n >= len(combos):
        return list(combos)
    return rng.sample(combos, n)


def run_one(combo, seed, safety_cap_secs, run_idx):
    workdir = pathlib.Path(tempfile.mkdtemp(prefix=f"dcss-throughput-{run_idx}-"))
    rc_text = RC_TMPL.read_text().replace("__COMBO__", combo)
    (workdir / "test.rc").write_text(rc_text)
    save_dir = workdir / "saves"
    morgue_dir = workdir / "morgue"
    save_dir.mkdir(exist_ok=True)
    morgue_dir.mkdir(exist_ok=True)

    # /usr/bin/time -v needs a real pty for crawl's console UI; script(1)
    # gives it one without pulling in pexpect (this runs in a worker
    # process, keep deps minimal). script -qec runs the command and quits;
    # -f flushes so the -v report survives even if we time out and kill it.
    inner = (
        f"{CRAWL_BIN} -lua-max-memory 128 -rc {workdir / 'test.rc'} -rcdir {QW_DIR} "
        f"-name t{run_idx} -seed {seed} -dir {save_dir} -morgue {morgue_dir} "
        f"-no-player-bones"
    )
    typescript = workdir / "typescript"
    cmd = ["script", "-qefc", f"/usr/bin/time -v {inner}", str(typescript)]

    result = {
        "combo": combo, "seed": seed, "run_idx": run_idx,
        "status": "unknown", "wall_secs": None, "user_secs": None,
        "sys_secs": None, "max_rss_kb": None, "rune_milestone": False,
        "milestone_types": [],
    }

    start = time.time()
    try:
        subprocess.run(
            cmd, cwd=workdir, timeout=safety_cap_secs,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        result["status"] = "completed"
    except subprocess.TimeoutExpired:
        result["status"] = "safety_cap_hit"
    result["wall_secs_measured"] = time.time() - start

    # `script`'s own stdout/stderr forwarding isn't reliable when its
    # controlling terminal is a pipe (observed empirically: proc.stderr came
    # back empty even though /usr/bin/time -v definitely ran) — the
    # typescript file it writes is the one place the -v report reliably
    # lands, so read timing from there instead of from the subprocess pipes.
    output = typescript.read_text(errors="replace") if typescript.exists() else ""
    for key, pattern in TIME_RE.items():
        m = pattern.search(output)
        if not m:
            continue
        if key == "wall_secs":
            h, mnt, s = m.groups()
            result[key] = (int(h) * 3600 if h else 0) + int(mnt) * 60 + float(s)
        else:
            result[key] = float(m.group(1)) if "." in pattern.pattern else int(m.group(1))

    if result["wall_secs"] is None and result["status"] == "safety_cap_hit":
        # time -v never got to print (process was killed mid-run) — use the
        # measured wall-clock as a censored-at-the-cap value so these runs
        # still count in the percentiles instead of silently vanishing.
        result["wall_secs"] = result["wall_secs_measured"]

    mfile = save_dir / "saves" / "milestones-seeded"
    if mfile.exists():
        types = re.findall(r"type=([a-z._]+)", mfile.read_text())
        result["milestone_types"] = types
        result["rune_milestone"] = "rune" in types

    import shutil
    shutil.rmtree(workdir, ignore_errors=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-games", type=int, default=50)
    ap.add_argument("--safety-cap-secs", type=int, default=900)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--sample-seed", type=int, default=42)
    ap.add_argument("--out", default=str(ROOT / "data/throughput-report.json"))
    args = ap.parse_args()

    if not CRAWL_BIN.exists():
        print(f"throughput-probe.py: {CRAWL_BIN} not found; build it first", file=sys.stderr)
        sys.exit(1)

    combos = sample_combos(args.n_games, args.sample_seed)
    print(f"sampled {len(combos)} combos, safety_cap={args.safety_cap_secs}s, workers={args.workers}")

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(run_one, combo, 1000 + i, args.safety_cap_secs, i): (combo, i)
            for i, combo in enumerate(combos)
        }
        for fut in as_completed(futs):
            combo, i = futs[fut]
            try:
                r = fut.result()
            except Exception as e:
                r = {"combo": combo, "run_idx": i, "status": "harness_exception", "error": str(e)}
            results.append(r)
            print(f"  [{len(results)}/{len(combos)}] {r.get('combo')} "
                  f"status={r.get('status')} wall={r.get('wall_secs')}s "
                  f"rune={r.get('rune_milestone')}")

    def pctile(vals, p):
        vals = sorted(v for v in vals if v is not None)
        if not vals:
            return None
        k = int(round((len(vals) - 1) * p))
        return vals[k]

    walls = [r.get("wall_secs") for r in results]
    users = [r.get("user_secs") for r in results]
    rsses = [r.get("max_rss_kb") for r in results]
    report = {
        "n_games": len(results),
        "safety_cap_secs": args.safety_cap_secs,
        "workers": args.workers,
        "sample_seed": args.sample_seed,
        "wall_secs": {"median": pctile(walls, 0.5), "p95": pctile(walls, 0.95)},
        "user_cpu_secs": {"median": pctile(users, 0.5), "p95": pctile(users, 0.95)},
        "max_rss_mb": {
            "median": (pctile(rsses, 0.5) or 0) / 1024,
            "p95": (pctile(rsses, 0.95) or 0) / 1024,
        },
        "safety_cap_hit_count": sum(1 for r in results if r.get("status") == "safety_cap_hit"),
        "rune_milestone_count": sum(1 for r in results if r.get("rune_milestone")),
        "runs": results,
    }

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {out_path}")
    print(f"wall_secs median={report['wall_secs']['median']} p95={report['wall_secs']['p95']}")
    print(f"max_rss_mb median={report['max_rss_mb']['median']:.1f} p95={report['max_rss_mb']['p95']:.1f}")
    print(f"safety_cap_hit={report['safety_cap_hit_count']}/{len(results)} rune_milestones={report['rune_milestone_count']}")


if __name__ == "__main__":
    main()
