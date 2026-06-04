"""Robust univariate background/threshold estimators with graceful degradation.

When MAD collapses to 0 (e.g. >50% identical / at-DL values), the threshold would
be degenerate and produce mass false positives; we auto-degrade to Tukey IQR,
and to a high quantile if IQR is also 0.
"""
import numpy as np

_MAD_SCALE = 1.4826


def mad(x):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    med = np.median(x)
    return _MAD_SCALE * np.median(np.abs(x - med))


def _quantile_threshold(x, q=0.975):
    thr = np.quantile(x, q)
    return thr, x > thr


def robust_threshold(values, method="mad", k=3.0, log=True, q=0.975):
    """Return dict {method_used, threshold, flags, note}."""
    x = np.asarray(values, dtype=float)
    finite = ~np.isnan(x)
    work = x[finite]
    note = ""
    if log:
        if (work <= 0).any():
            work = work + (abs(work.min()) + 1e-9 if work.min() <= 0 else 0)
        work = np.log(work)
        xx = np.log(np.where(x > 0, x, np.nan))
    else:
        xx = x

    method_used = method
    if method == "mad":
        m = mad(work)
        if m == 0:
            note = "MAD==0 -> degraded"
            method_used = "tukey"
        else:
            thr = np.median(work) + k * m
            flags = xx > thr
            return {"method_used": "mad", "threshold": float(thr),
                    "flags": np.where(np.isnan(xx), False, flags), "note": note}

    if method_used in ("tukey",) or method == "tukey":
        q1, q3 = np.percentile(work, [25, 75])
        iqr = q3 - q1
        if iqr == 0:
            note = (note + "; ") if note else ""
            note += "IQR==0 -> quantile"
            thr = np.quantile(work, q)
            flags = work > thr
            mask = np.where(np.isnan(xx), False, xx > thr)
            return {"method_used": "quantile", "threshold": float(thr), "flags": mask,
                    "note": note}
        thr = q3 + 1.5 * iqr
        mask = np.where(np.isnan(xx), False, xx > thr)
        return {"method_used": "tukey", "threshold": float(thr), "flags": mask, "note": note}

    if method == "quantile":
        thr = np.quantile(work, q)
        mask = np.where(np.isnan(xx), False, xx > thr)
        return {"method_used": "quantile", "threshold": float(thr), "flags": mask, "note": note}

    raise ValueError(f"unknown method {method!r}")
