"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def _check_pair(human: Sequence[str], judge: Sequence[str]) -> None:
    if len(human) != len(judge):
        raise ValueError(f"length mismatch: {len(human)} human labels vs {len(judge)} judge labels")


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    _check_pair(human, judge)
    tp = fp = fn = tn = 0
    for h, j in zip(human, judge):
        h_pos, j_pos = h == POS, j == POS
        if h_pos and j_pos:
            tp += 1
        elif j_pos:
            fp += 1
        elif h_pos:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    tp, fp, fn = cm["tp"], cm["fp"], cm["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    _check_pair(human, judge)
    n = len(human)
    if n == 0:
        raise ValueError("kappa undefined for an empty sample")
    p_o = sum(h == j for h, j in zip(human, judge)) / n
    p_e = sum((sum(h == c for h in human) / n) * (sum(j == c for j in judge) / n)
              for c in set(human) | set(judge))
    if math.isclose(p_e, 1.0):
        raise ValueError("kappa undefined: chance agreement is 1 (constant labels)")
    return (p_o - p_e) / (1 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1
    if denom <= 0:
        raise ValueError("judge no better than chance (sensitivity + specificity <= 1): cannot correct")
    return min(1.0, max(0.0, (observed_rate + specificity - 1) / denom))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy import stats as sps

    if len(a) != len(b):
        raise ValueError("paired bootstrap needs the same items in the same order")
    if len(a) == 0:
        raise ValueError("paired bootstrap needs at least one item")
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    diff = x - y
    if np.all(diff == 0):
        return (0.0, 0.0, 0.0)
    mean_diff = float(diff.mean())
    if np.all(diff == diff[0]) or len(x) < 2:
        return (mean_diff, mean_diff, mean_diff)      # no spread to resample
    res = sps.bootstrap((x, y), lambda u, v, axis: np.mean(u - v, axis=axis), paired=True,
                        n_resamples=n_resamples, confidence_level=confidence, method="percentile",
                        rng=np.random.default_rng(rng))
    return (mean_diff, float(res.confidence_interval.low), float(res.confidence_interval.high))


def _check_nck(n: int, c: int, k: int) -> None:
    if not (isinstance(n, int) and isinstance(c, int) and isinstance(k, int)):
        raise ValueError("n, c, k must be integers")
    if k < 1 or n < 1 or k > n:
        raise ValueError(f"need 1 <= k <= n (got n={n}, k={k})")
    if c < 0 or c > n:
        raise ValueError(f"need 0 <= c <= n (got n={n}, c={c})")


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _check_nck(n, c, k)
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _check_nck(n, c, k)
    return math.comb(c, k) / math.comb(n, k)
