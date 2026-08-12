#!/usr/bin/env python3
"""PLAN.md §8 experiment protocol scaffolding. Phase 2 items are hypotheses
until measured through this, not ad hoc before/after comparisons — this
module must exist before the first Phase 2 experiment runs (see
docs/JOURNAL.md's Phase 1 exit review).

Three pieces, matching §8's list:

1. **Seed splits** (`split_seed`, `seeds_for_split`): deterministic
   dev/validation/holdout partitioning of a seed range, so a split doesn't
   need a stored membership list and can't drift between the seeds used to
   *develop* a fix and the seeds used to *validate* it — §8: "Identifying
   weak buckets and validating their fixes on the same campaign data is
   overfitting; bucket-targeted fixes are confirmed on fresh seeds."
2. **Pre-declaration file format** (`declare_experiment`,
   `Predeclaration`): primary outcome, minimum practically-meaningful
   effect, sample size, and seed split are all written to disk *before* any
   arm is run, and the file is refused a second write — a pre-declaration
   that could be edited after seeing results isn't one.
3. **Effect-size / CI comparison** (`wilson_interval`,
   `two_proportion_diff_ci`): stdlib-only (no scipy/numpy in this
   environment, matching ops/sampler-test.py's existing chi-square
   approach) Wilson score intervals per arm and a Newcombe-Wilson hybrid CI
   for the between-arm difference, used to check a result against its own
   pre-declared minimum effect.

This module is intentionally generic over "primary outcome" — it operates
on plain (successes, n) proportions, not on the DB schema directly. A
caller (e.g. a Phase 2 experiment script) computes the proportion for its
declared metric from ops/collector.py's SQLite output and passes it in
here.

Library use: `split_seed`, `declare_experiment`, `load_predeclaration`,
`wilson_interval`, `two_proportion_diff_ci`, `evaluate_predeclaration`.
"""
import dataclasses
import hashlib
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_EXPERIMENTS_DIR = ROOT / "data/experiments"

SPLITS = ("dev", "validation", "holdout")
# §8 doesn't mandate exact proportions; this default gives holdout enough
# games to detect the kind of effect sizes §8 describes (hundreds-to-
# thousands per arm) while keeping dev the largest bucket, since dev seeds
# are "used freely" and validation/holdout are spent more sparingly.
DEFAULT_SPLIT_WEIGHTS = {"dev": 0.6, "validation": 0.2, "holdout": 0.2}


def split_seed(seed, weights=None, salt="dcss-automation-seed-split"):
    """Deterministically assign one seed (an int, e.g. a char_seed) to
    'dev', 'validation', or 'holdout'. Pure function of (seed, weights,
    salt) -- no stored membership list, so it can't silently drift from
    what a report recomputes later, and is trivially reproducible from a
    predeclaration file alone (§8: "reproducible from its manifest alone").

    Uses a hash, not seed % N: seed values are frequently allocated in
    contiguous ranges (e.g. campaign.py's char_seed_base + i), and a
    modulus would correlate split membership with allocation order (every
    5th seed always dev, say) -- a hash decorrelates split membership from
    however seeds happen to be numbered."""
    weights = weights or DEFAULT_SPLIT_WEIGHTS
    total = sum(weights[s] for s in SPLITS)
    digest = hashlib.sha256(f"{salt}:{seed}".encode()).digest()
    # top 8 bytes as an integer -> uniform float in [0, 1)
    frac = int.from_bytes(digest[:8], "big") / 2**64
    cursor = 0.0
    threshold = frac * total
    for name in SPLITS:
        cursor += weights[name]
        if threshold < cursor:
            return name
    return SPLITS[-1]  # floating-point edge case at the top boundary


def seeds_for_split(split, seed_range, weights=None, salt="dcss-automation-seed-split"):
    """All seeds in seed_range (an iterable of ints, e.g. range(a, b)) that
    fall in the given split. Convenience wrapper around split_seed for
    campaign launch scripts that want a concrete list to drive
    --char-seed-base/--index-start from."""
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}, want one of {SPLITS}")
    return [s for s in seed_range if split_seed(s, weights, salt) == split]


@dataclasses.dataclass
class Predeclaration:
    name: str
    hypothesis: str
    primary_outcome: str
    direction: str  # "increase" or "decrease" -- which way is "better"
    minimum_effect: float  # in absolute proportion points, e.g. 0.02 = 2pts
    alpha: float
    arms: dict  # {arm_name: {description, config}}
    seed_split: str  # one of SPLITS
    sample_size_per_arm: int
    baseline_ref: str  # e.g. "data/phase1-500.db" -- the frozen baseline this compares against

    def to_json(self):
        return json.dumps(dataclasses.asdict(self), indent=2, sort_keys=True)


def declare_experiment(predecl, experiments_dir=DEFAULT_EXPERIMENTS_DIR):
    """Write predecl to data/experiments/<name>/predeclaration.json. Refuses
    to overwrite an existing file -- §8's whole point is that primary
    outcome / minimum effect / sample size are fixed *before* any arm runs;
    an editable predeclaration is not a predeclaration."""
    if predecl.direction not in ("increase", "decrease"):
        raise ValueError(f"direction must be 'increase' or 'decrease', got {predecl.direction!r}")
    if predecl.seed_split not in SPLITS:
        raise ValueError(f"seed_split must be one of {SPLITS}, got {predecl.seed_split!r}")
    out_dir = pathlib.Path(experiments_dir) / predecl.name
    out_path = out_dir / "predeclaration.json"
    if out_path.exists():
        raise FileExistsError(
            f"{out_path} already exists -- predeclarations are write-once; "
            "start a new experiment name instead of editing this one")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(predecl.to_json() + "\n")
    return out_path


def load_predeclaration(name, experiments_dir=DEFAULT_EXPERIMENTS_DIR):
    path = pathlib.Path(experiments_dir) / name / "predeclaration.json"
    return Predeclaration(**json.loads(path.read_text()))


def _norm_ppf(p):
    """Inverse standard normal CDF (Acklam's algorithm, ~1e-9 accuracy).
    Same approximation as ops/sampler-test.py's _norm_ppf (stdlib-only, no
    scipy/numpy in this environment) -- duplicated rather than imported
    since sampler-test.py is a test entry point, not a library module."""
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


def wilson_interval(successes, n, alpha=0.05):
    """Wilson score confidence interval for a binomial proportion. More
    reliable than the naive normal-approximation interval at the low base
    rates §8 calls out (rune-rate, lua_error-rate), including the
    successes=0 edge case a Wald interval degenerates on."""
    if n == 0:
        return (0.0, 1.0)
    z = _norm_ppf(1 - alpha / 2)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def two_proportion_diff_ci(x1, n1, x2, n2, alpha=0.05):
    """Newcombe's hybrid-score CI (Newcombe 1998, method 10) for p1 - p2,
    built from each arm's own Wilson interval. Preferred over a pooled
    z-test at the sample sizes/rates this project's §8 experiments run at
    (hundreds-to-thousands per arm, often single-digit-percent rates) --
    it stays well-behaved down to zero successes in an arm, where a pooled
    normal-approximation interval does not."""
    p1, p2 = x1 / n1, x2 / n2
    l1, u1 = wilson_interval(x1, n1, alpha)
    l2, u2 = wilson_interval(x2, n2, alpha)
    diff = p1 - p2
    lo = diff - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = diff + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (lo, hi)


def evaluate_predeclaration(predecl, arm_counts):
    """arm_counts: {arm_name: (successes, n)} for the predeclared
    primary_outcome. Returns a dict: per-arm rate + Wilson CI, the
    treatment-vs-control diff + Newcombe CI, and whether the result clears
    the predeclared minimum_effect in the predeclared direction with the
    CI excluding zero (the §8 "improvement" bar: "rune-rate +X pts
    CI-excluding zero"). Assumes exactly two arms; the first alphabetically
    that isn't named 'control'/'baseline' is treated as treatment if there
    are exactly two and neither is literally named 'control' -- pass
    unambiguous arm names to avoid relying on that."""
    if set(arm_counts) != set(predecl.arms):
        raise ValueError(f"arm_counts keys {set(arm_counts)} != predeclared arms {set(predecl.arms)}")
    if len(arm_counts) != 2:
        raise ValueError("evaluate_predeclaration only supports exactly two arms")
    names = sorted(arm_counts)
    control = "control" if "control" in names else names[0]
    treatment = next(n for n in names if n != control)

    xc, nc = arm_counts[control]
    xt, nt = arm_counts[treatment]
    rate_c, ci_c = xc / nc, wilson_interval(xc, nc, predecl.alpha)
    rate_t, ci_t = xt / nt, wilson_interval(xt, nt, predecl.alpha)
    diff = rate_t - rate_c
    diff_ci = two_proportion_diff_ci(xt, nt, xc, nc, predecl.alpha)

    signed_diff = diff if predecl.direction == "increase" else -diff
    signed_lo = diff_ci[0] if predecl.direction == "increase" else -diff_ci[1]
    clears_min_effect = signed_diff >= predecl.minimum_effect
    ci_excludes_zero = signed_lo > 0

    return {
        "control_arm": control, "treatment_arm": treatment,
        "control_rate": rate_c, "control_ci": ci_c,
        "treatment_rate": rate_t, "treatment_ci": ci_t,
        "diff_treatment_minus_control": diff, "diff_ci": diff_ci,
        "clears_minimum_effect": clears_min_effect,
        "ci_excludes_zero_in_declared_direction": ci_excludes_zero,
        "declared_improvement": clears_min_effect and ci_excludes_zero,
    }


if __name__ == "__main__":
    print(__doc__, file=sys.stderr)
    sys.exit(1)
