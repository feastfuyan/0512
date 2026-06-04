"""Non-detect detection (isotope-safe, per-column) and Helsel ROS imputation.

Detection of censoring lives HERE (single source of truth). Imputation method is
chosen by shared config and reported by callers. We never apply a global
negative==ND rule, because isotope deltas are legitimately negative.
"""
import numpy as np
import pandas as pd
from scipy import stats


def is_isotope_column(col_name, iso_tokens):
    low = col_name.lower()
    return any(tok in low for tok in iso_tokens)


def detect_censored(series, col_name, iso_tokens, neg_is_nd=False):
    """Return (flags: bool Series, clean: float Series with DL level at censored cells).

    Rules:
      - isotope columns: never censored (legit negatives), parsed numeric as-is.
      - text like '<5' -> censored, level = 5.
      - numeric negatives -> censored ONLY if neg_is_nd=True AND not isotope.
      - everything else -> detected numeric.
    Conservative: an unparseable cell raises ValueError (do not guess).
    """
    iso = is_isotope_column(col_name, iso_tokens)
    flags = np.zeros(len(series), dtype=bool)
    clean = np.empty(len(series), dtype=float)
    for i, v in enumerate(series.tolist()):
        if pd.isna(v):
            clean[i] = np.nan
            continue
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("<"):
                if iso:
                    raise ValueError(f"'<' censoring on isotope column {col_name!r}: {v!r}")
                flags[i] = True
                clean[i] = float(s[1:])
            else:
                clean[i] = float(s)          # raises if unparseable -> conservative
        else:
            fv = float(v)
            if (not iso) and neg_is_nd and fv < 0:
                flags[i] = True
                clean[i] = abs(fv)
            else:
                clean[i] = fv
    return pd.Series(flags, index=series.index), pd.Series(clean, index=series.index)


def ros_impute(values, censored, log=True):
    """Regression on Order Statistics (single-DL simplification, Helsel)."""
    values = np.asarray(values, dtype=float)
    censored = np.asarray(censored, dtype=bool)
    n = len(values)
    if censored.sum() == 0:
        return values.copy()
    if censored.all():
        return values / 2.0
    order = np.argsort(values, kind="mergesort")
    v = values[order]
    c = censored[order]
    pp = (np.arange(1, n + 1)) / (n + 1)          # Weibull plotting positions
    xq = stats.norm.ppf(pp[~c])
    y = np.log(v[~c]) if log else v[~c]
    slope, intercept, *_ = stats.linregress(xq, y)
    out = v.copy()
    cen = np.where(c)[0]
    pred = intercept + slope * stats.norm.ppf(pp[cen])
    out[cen] = np.exp(pred) if log else pred
    result = np.empty(n)
    result[order] = out
    return result


def detect_dl_floor(values, min_fraction=0.10, min_count=3):
    """Heuristic DL-floor: a pile-up of identical values at a POSITIVE column minimum
    (labs reporting below-DL as the DL value). Returns (floor_value, count) if
    >= min_fraction of finite values tie at the minimum and count >= min_count, else (None, 0)."""
    import numpy as np
    v = np.asarray([x for x in values if x is not None and not (isinstance(x, float) and np.isnan(x))], dtype=float)
    v = v[~np.isnan(v)]
    if v.size == 0:
        return None, 0
    mn = float(v.min())
    if mn <= 0:
        return None, 0
    count = int((v == mn).sum())
    if count >= min_count and count / v.size >= min_fraction:
        return mn, count
    return None, 0


def substitute(values, censored, rule="half_dl"):
    """Static substitution at the DL level stored in `values`."""
    values = np.asarray(values, dtype=float)
    censored = np.asarray(censored, dtype=bool)
    out = values.copy()
    factor = {"half_dl": 0.5, "sqrt_dl": 1.0 / np.sqrt(2)}[rule]
    out[censored] = values[censored] * factor
    return out
