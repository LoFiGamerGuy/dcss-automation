#!/usr/bin/env python3
"""Phase 1 sampler acceptance tests (PLAN.md §2 / §9 Phase 1 exit):

1. Support-set diff: the combo/weapon-choice sets the sampler draws from
   (data/manifests/legal-characters.json) exactly match what the pinned
   binary reports *right now* via -playable-json/-weapon-json — empty diff,
   not "a manifest exists". Re-checked here (not just at generation time)
   because the manifest is a committed file that could silently drift from
   the binary it's supposed to describe.
2. Determinism: same (manifest, char_seed) always samples the same character.
3. Goodness-of-fit: at campaign scale (default 200k samples), pair selection
   is uniform over all legal combos, and — conditional on landing on a given
   weapon-choice combo — weapon selection is uniform over that combo's
   options. Chi-square tests computed from stdlib only (no scipy/numpy in
   this environment); critical values via the Wilson-Hilferty chi-square
   approximation (accurate for the largeish degrees-of-freedom here) driven
   by a stdlib-only normal-quantile function (Acklam's algorithm).

Usage: sampler-test.py [--n-samples N] [--alpha F] [--seed-base N]
Exit 0 and prints "PASS" on success; exit 1 with the failed assertion(s) on
failure.
"""
import argparse
import json
import math
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
import combos  # noqa: E402

CRAWL_BIN = ROOT / "vendor/crawl/crawl-ref/source/crawl"


def _norm_ppf(p):
    """Inverse standard normal CDF (Acklam's algorithm, ~1e-9 accuracy)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    p_low = 0.02425
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > 1 - p_low:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _chi2_critical(df, alpha):
    """Wilson-Hilferty approximation to the upper-tail chi-square quantile."""
    z = _norm_ppf(1 - alpha)
    return df * (1 - 2 / (9 * df) + z * math.sqrt(2 / (9 * df))) ** 3


def _chi2_stat(observed_counts, expected):
    return sum((o - expected) ** 2 / expected for o in observed_counts)


def check_support_set(manifest):
    if not CRAWL_BIN.exists():
        return [f"SKIP support-set diff: {CRAWL_BIN} not built"]
    playable = json.loads(subprocess.check_output([str(CRAWL_BIN), "-playable-json"]))
    weapons = json.loads(subprocess.check_output([str(CRAWL_BIN), "-weapon-json"]))

    failures = []
    live_combos = set(playable["combos"])
    manifest_combos = set(manifest["combos"])
    if live_combos != manifest_combos:
        failures.append(
            "combo set diff vs live binary: "
            f"missing_from_manifest={live_combos - manifest_combos} "
            f"extra_in_manifest={manifest_combos - live_combos}"
        )

    live_weapon_combos = {w["combo"]: set(w["weapons"]) for w in weapons}
    manifest_weapon_combos = {w["combo"]: set(w["weapons"]) for w in manifest["weapon_choices"]}
    if set(live_weapon_combos) != set(manifest_weapon_combos):
        failures.append(
            "weapon-choice combo set diff vs live binary: "
            f"missing_from_manifest={set(live_weapon_combos) - set(manifest_weapon_combos)} "
            f"extra_in_manifest={set(manifest_weapon_combos) - set(live_weapon_combos)}"
        )
    else:
        for combo, live_set in live_weapon_combos.items():
            if manifest_weapon_combos[combo] != live_set:
                failures.append(
                    f"weapon options for {combo!r} diff vs live binary: "
                    f"manifest={manifest_weapon_combos[combo]} live={live_set}"
                )
    return failures


def check_determinism(manifest, digest, seed_base):
    failures = []
    for seed in (seed_base, seed_base + 1, seed_base + 999999):
        a = combos.sample_character(manifest, digest, seed)
        b = combos.sample_character(manifest, digest, seed)
        if a != b:
            failures.append(f"char_seed={seed} sampled two different characters: {a} vs {b}")
    return failures


def check_goodness_of_fit(manifest, digest, n_samples, alpha, seed_base):
    failures = []
    weapon_lookup = combos.weapon_index(manifest)
    pairs = manifest["combos"]
    n_pairs = len(pairs)

    pair_counts = {p: 0 for p in pairs}
    weapon_counts = {}  # combo -> [count per weapon index]
    for i in range(n_samples):
        r = combos.sample_character(manifest, digest, seed_base + i, weapon_lookup)
        pair_counts[r["combo"]] += 1
        if r["weapon"] is not None:
            wc = weapon_counts.setdefault(r["combo"], [0] * len(weapon_lookup[r["combo"]]))
            wc[r["weapon_index"]] += 1

    # 1. Pair-selection uniformity: single test, df = n_pairs - 1.
    expected_per_pair = n_samples / n_pairs
    stat = _chi2_stat(pair_counts.values(), expected_per_pair)
    crit = _chi2_critical(n_pairs - 1, alpha)
    if stat > crit:
        worst = sorted(pair_counts.items(), key=lambda kv: abs(kv[1] - expected_per_pair))[-5:]
        failures.append(
            f"pair-selection chi2={stat:.1f} exceeds critical={crit:.1f} "
            f"(df={n_pairs - 1}, alpha={alpha}, expected/pair={expected_per_pair:.1f}); "
            f"worst-fitting pairs={worst}"
        )

    # 2. Weapon-selection uniformity, conditional on combo: one test per combo
    # with enough observations for a valid chi-square (expected count >= 5 in
    # every bin); Bonferroni-corrected across however many combos qualify, so
    # running many independent per-combo tests doesn't inflate the false-
    # positive rate.
    # len(counts) == 1 means the manifest lists exactly one "choice" (e.g.
    # Felid combos, which only ever offer "unarmed") — not a real
    # distribution to test uniformity over, so df would be 0.
    testable = {c: counts for c, counts in weapon_counts.items()
                if len(counts) >= 2 and sum(counts) / len(counts) >= 5}
    if testable:
        per_test_alpha = alpha / len(testable)
        for combo, counts in testable.items():
            n = sum(counts)
            expected = n / len(counts)
            stat = _chi2_stat(counts, expected)
            crit = _chi2_critical(len(counts) - 1, per_test_alpha)
            if stat > crit:
                failures.append(
                    f"weapon-selection for {combo!r} chi2={stat:.1f} exceeds "
                    f"critical={crit:.1f} (df={len(counts) - 1}, "
                    f"per_test_alpha={per_test_alpha:.2e}, counts={counts})"
                )
    else:
        failures.append(
            f"no weapon-choice combo reached >=5 expected count per weapon bin "
            f"in {n_samples} samples — increase --n-samples"
        )

    return failures, {"n_pairs": n_pairs, "weapon_combos_tested": len(testable)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-samples", type=int, default=200_000)
    ap.add_argument("--alpha", type=float, default=0.001)
    ap.add_argument("--seed-base", type=int, default=0)
    args = ap.parse_args()

    manifest, digest = combos.load_manifest()
    failures = []

    failures += check_support_set(manifest)
    failures += check_determinism(manifest, digest, args.seed_base)
    gof_failures, gof_info = check_goodness_of_fit(
        manifest, digest, args.n_samples, args.alpha, args.seed_base + 10_000_000
    )
    failures += gof_failures

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print(
        f"PASS: support-set matches live binary, sampling is deterministic, "
        f"and pair/weapon selection pass goodness-of-fit at alpha={args.alpha} "
        f"(n_samples={args.n_samples}, n_pairs={gof_info['n_pairs']}, "
        f"weapon_combos_tested={gof_info['weapon_combos_tested']})"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
