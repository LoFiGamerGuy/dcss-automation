#!/usr/bin/env python3
"""Self-test for ops/experiment.py's §8 scaffolding: seed-split determinism
and non-overlap, Wilson/Newcombe interval sanity against known reference
values, and the pre-declaration file's write-once contract.

Usage: experiment-test.py
Exit 0 and prints "PASS" on success; exit 1 with the failure(s) on failure.
"""
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
import experiment as exp  # noqa: E402

failures = []


def check(name, cond, detail=""):
    status = "ok  " if cond else "FAIL"
    print(f"{status} {name}" + (f": {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(f"{name}: {detail}")


def test_split_determinism():
    seeds = range(0, 5000)
    first = {s: exp.split_seed(s) for s in seeds}
    second = {s: exp.split_seed(s) for s in seeds}
    check("split_seed is deterministic", first == second)


def test_split_proportions_and_disjoint():
    seeds = list(range(0, 20000))
    counts = {"dev": 0, "validation": 0, "holdout": 0}
    for s in seeds:
        counts[exp.split_seed(s)] += 1
    n = len(seeds)
    # Loose tolerance (+/-3 percentage points) -- this is a sanity check on
    # the hash-based assignment, not a goodness-of-fit test (sampler-test.py
    # already owns rigorous chi-square testing elsewhere in this repo).
    for name, weight in exp.DEFAULT_SPLIT_WEIGHTS.items():
        frac = counts[name] / n
        check(f"split {name!r} proportion near {weight}", abs(frac - weight) < 0.03,
              f"got {frac:.4f}")

    dev = set(exp.seeds_for_split("dev", seeds))
    val = set(exp.seeds_for_split("validation", seeds))
    hold = set(exp.seeds_for_split("holdout", seeds))
    check("splits are pairwise disjoint",
          not (dev & val) and not (dev & hold) and not (val & hold))
    check("splits cover every seed", dev | val | hold == set(seeds))


def test_split_salt_changes_assignment():
    seeds = range(0, 2000)
    a = [exp.split_seed(s, salt="experiment-a") for s in seeds]
    b = [exp.split_seed(s, salt="experiment-b") for s in seeds]
    frac_same = sum(1 for x, y in zip(a, b) if x == y) / len(a)
    # With 3 roughly-weighted buckets, two independent salts agreeing on
    # ~1/3 of seeds by chance is expected -- assert it's NOT near-identical
    # (which would mean salt isn't actually doing anything).
    check("different salts decorrelate split membership", frac_same < 0.6,
          f"frac_same={frac_same:.3f}")


def test_wilson_interval_known_values():
    # Reference computed by hand from the Wilson score formula directly
    # (p=0.25, n=20, z=1.959964): center=(p+z^2/2n)/(1+z^2/n)=0.29027,
    # half-width=0.178417 -> (0.11185, 0.46869). Cross-checks this module's
    # implementation against the formula, not against another library.
    lo, hi = exp.wilson_interval(5, 20, alpha=0.05)
    check("wilson_interval(5, 20) matches hand-computed reference",
          abs(lo - 0.11185) < 0.0005 and abs(hi - 0.46869) < 0.0005,
          f"got ({lo:.4f}, {hi:.4f})")
    # n=0 edge case shouldn't crash and should be maximally uninformative.
    lo0, hi0 = exp.wilson_interval(0, 0)
    check("wilson_interval(0, 0) is the full [0,1] range", (lo0, hi0) == (0.0, 1.0))
    # 0 successes shouldn't crash (Wald interval degenerates to a point here).
    lo_z, hi_z = exp.wilson_interval(0, 100)
    check("wilson_interval(0, 100) lower bound is 0, upper bound > 0",
          lo_z == 0.0 and hi_z > 0, f"got ({lo_z}, {hi_z})")


def test_two_proportion_diff_ci_sanity():
    # Identical arms -> point estimate of the difference is 0 and the CI
    # straddles 0.
    lo, hi = exp.two_proportion_diff_ci(50, 500, 50, 500)
    check("identical arms: diff CI straddles 0", lo < 0 < hi, f"got ({lo:.4f}, {hi:.4f})")

    # A large, obvious effect (5% vs 30% at n=500 each) should have a CI
    # entirely on one side of 0.
    lo2, hi2 = exp.two_proportion_diff_ci(25, 500, 150, 500)  # treatment=5%, control=30%
    check("large effect: diff CI excludes 0", hi2 < 0, f"got ({lo2:.4f}, {hi2:.4f})")


def test_predeclaration_write_once_and_evaluate():
    with tempfile.TemporaryDirectory(prefix="dcss-experiment-test-") as tmp:
        exp_dir = pathlib.Path(tmp)
        predecl = exp.Predeclaration(
            name="synthetic-test", hypothesis="treatment reduces failure rate",
            primary_outcome="failure_rate", direction="decrease", minimum_effect=0.05,
            alpha=0.05, arms={"control": {}, "treatment": {}}, seed_split="validation",
            sample_size_per_arm=300, baseline_ref="data/phase1-500.db",
        )
        path = exp.declare_experiment(predecl, experiments_dir=exp_dir)
        check("declare_experiment writes the file", path.exists())

        try:
            exp.declare_experiment(predecl, experiments_dir=exp_dir)
            check("declare_experiment refuses to overwrite", False, "no exception raised")
        except FileExistsError:
            check("declare_experiment refuses to overwrite", True)

        loaded = exp.load_predeclaration("synthetic-test", experiments_dir=exp_dir)
        check("load_predeclaration round-trips", loaded == predecl, f"got {loaded}")

        # control fails 100/300 (33%), treatment fails 60/300 (20%) -- a
        # 13pt reduction, comfortably clearing the 5pt minimum_effect.
        result = exp.evaluate_predeclaration(loaded, {"control": (100, 300), "treatment": (60, 300)})
        check("evaluate_predeclaration: clear improvement is declared",
              result["declared_improvement"] is True, f"got {result}")

        # Now a negligible difference (100/300 vs 95/300) shouldn't clear
        # the bar.
        result2 = exp.evaluate_predeclaration(loaded, {"control": (100, 300), "treatment": (95, 300)})
        check("evaluate_predeclaration: negligible difference is not declared",
              result2["declared_improvement"] is False, f"got {result2}")


def main():
    test_split_determinism()
    test_split_proportions_and_disjoint()
    test_split_salt_changes_assignment()
    test_wilson_interval_known_values()
    test_two_proportion_diff_ci_sanity()
    test_predeclaration_write_once_and_evaluate()

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("PASS: seed splits, interval math, and predeclaration write-once contract all verified")
    sys.exit(0)


if __name__ == "__main__":
    main()
