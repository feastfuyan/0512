"""Spatial local-background anomaly via k nearest neighbours.

Compares each sample to a robust (median/MAD) estimate of its k nearest
neighbours, which removes a smooth regional trend so that LOCAL highs (halos,
spot anomalies) stand out without the regional gradient causing false positives.
This is spatial statistics, not mapping (mapping is out of scope).
"""
import numpy as np
from scipy.spatial import cKDTree

_MAD_SCALE = 1.4826


def knn_local_background(coords, values, k=8):
    """Return (local_background, local_anomaly_z).

    local_anomaly_z = (value - neighbour_median) / (scaled neighbour MAD).
    Samples with degenerate (zero) neighbour MAD get anomaly 0.
    """
    coords = np.asarray(coords, dtype=float)
    values = np.asarray(values, dtype=float)
    n = len(values)
    valid = ~np.isnan(coords).any(axis=1)
    tree = cKDTree(coords[valid])
    idx_map = np.where(valid)[0]
    local_bg = np.full(n, np.nan)
    local_anom = np.zeros(n)
    kk = min(k + 1, valid.sum())
    for i in range(n):
        if not valid[i]:
            continue
        _, nn = tree.query(coords[i], k=kk)
        nn = np.atleast_1d(nn)
        neigh = idx_map[nn]
        neigh = neigh[neigh != i]
        nv = values[neigh]
        med = np.median(nv)
        m = _MAD_SCALE * np.median(np.abs(nv - med))
        local_bg[i] = med
        local_anom[i] = (values[i] - med) / m if m > 0 else 0.0
    return local_bg, local_anom
