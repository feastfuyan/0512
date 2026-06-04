"""Weighted pathfinder scoring: score = sum_i w_i * normalized_anomaly_i.

Weights are deposit-system specific (orogenic gold weights per W. Wang review).
Produces a single sortable target score that also feeds ML (Phase 4).
"""
import numpy as np

PATHFINDER_WEIGHTS = {
    "orogenic_gold": {"As": 0.30, "Sb": 0.25, "Bi": 0.20, "Te": 0.15, "W": 0.10},
    # porphyry: distal landable shell (Re/Se rarely measured in routine packages)
    "porphyry_cu":  {"Mo": 0.30, "Au": 0.20, "Pb": 0.15, "Zn": 0.15, "As": 0.10, "Sb": 0.10},
    "vms":          {"Zn": 0.30, "Pb": 0.25, "Ba": 0.20, "Tl": 0.15, "Hg": 0.10},
    "iocg":         {"Cu": 0.25, "Co": 0.20, "U": 0.15, "La": 0.10, "Ce": 0.10, "P": 0.10, "F": 0.10},
    # NOTE: LCT pegmatites are best vectored by fractionation RATIOS (K/Rb, Nb/Ta, Mg/Li);
    # this single-element weighted score is a COARSE screen only — see pathfinders.md caveat.
    "li_pegmatite": {"Cs": 0.30, "Rb": 0.20, "Ta": 0.15, "Sn": 0.15, "Be": 0.10, "Nb": 0.10},
    "epithermal_au":{"As": 0.25, "Sb": 0.20, "Hg": 0.20, "Tl": 0.15, "Se": 0.10, "Ag": 0.10},
}


def pathfinder_score(anomalies, system, renormalize=False):
    """anomalies: dict element -> 1D array of normalized anomaly values.
    Returns 1D array of weighted-sum scores."""
    if system not in PATHFINDER_WEIGHTS:
        raise KeyError(f"unknown pathfinder system {system!r}")
    weights = PATHFINDER_WEIGHTS[system]
    present = {el: w for el, w in weights.items() if el in anomalies}
    if not present:
        raise ValueError(f"no pathfinder elements for {system!r} present in data")
    if renormalize:
        total = sum(present.values())
        present = {el: w / total for el, w in present.items()}
    n = len(next(iter(anomalies.values())))
    score = np.zeros(n)
    for el, w in present.items():
        score += w * np.asarray(anomalies[el], dtype=float)
    return score
