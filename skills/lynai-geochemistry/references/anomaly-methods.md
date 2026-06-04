# Anomaly & Background Methods (robust + fractal + spatial + compositional)

> Methods in `scripts/anomaly.py`. Robust estimators by default — classic mean/SD and classic
> Mahalanobis are inflated by the very anomalies you seek.

## Background vs threshold
Separate **regional background** (lithology/trend) from **local background** (neighbourhood). An
anomaly is an excess over the appropriate background, not over a global mean. [src: V13/Exploration Geochemistry; ref: Rose, Hawkes & Webb 1979]

## Population partitioning first
Before a single threshold, inspect the **probability plot** (log-probability) — inflections reveal
multiple populations (background vs mineralized vs contamination). Do not threshold a multi-modal
dataset with one cutoff. [ref: Sinclair 1974]

## Univariate robust thresholds (`--method`)
- **Median ± k·MAD** (default, k≈2–3; MAD ×1.4826) — robust to ~50% outliers. [ref: Reimann et al. 2008]
- **Tukey IQR** (Q3 + 1.5·IQR) · **log + k·σ** (log-normal trace data) · **percentile/CDF breaks** (95/97.5/99).
- **MAD=0 fallback** — >50% identical/at-DL → auto-degrade to Tukey, then high quantile; flagged in JSON `note`. [implemented: robust_stats.py]

## Fractal / multifractal thresholds (capture spatial structure pure stats miss)
- **Concentration–Area (C–A)** — log-log of concentration vs area above threshold; straight-line
  segments = distinct populations; breakpoints = thresholds. [ref: Cheng, Agterberg & Ballantyne 1994]
- **Spectrum–Area (S–A)** — frequency-domain separation of anomaly from regional (low-frequency) background. [ref: Cheng 1999]
- Use C–A/S–A ALONGSIDE robust stats and cross-check. [ref: Carranza 2009]

## Censored (<DL) data
Detect + flag once in QC (single source of truth). Default impute = **ROS**; simple substitution
(DL/2, DL/√2) is biased at high censoring and must be flagged. High censoring → lrEM/lrDA (see compositional-data.md). [ref: Helsel 2012]

## Spatial local background (`--spatial-mode knn`)
- **KNN local background** — compare each sample to robust (median/MAD) of its k nearest neighbours;
  removes smooth regional trend so LOCAL highs stand out and a regional gradient does NOT false-flag.
  Default k=8. [implemented: spatial.py]
- ⚠️ **Anomalous-core erasure** — if a mineralized halo is LARGER than the k-neighbourhood, the
  neighbour median is itself elevated and the core is subtracted away as "background" (core local-anomaly
  WEAKER than its edges). **Rule:** when local anomaly at a high-value centre is weaker than its rim,
  cross-check the GLOBAL anomaly and flag a "矿心区 core-erasure 复核" in report Section 3; consider larger
  k, regional-background subtraction, or kriging residual.
- **Trend-surface / LOESS residual** (Phase 1.5) · **immobile-element background removal** (ratio/regress
  mobile elements against Zr/Al/Ti/Th/Sc to correct clastic dilution / medium effects). [src: V13/Exploration Geochemistry]

## Contamination / spatial-control screen (`--contam-coords` / `--contam-covariate`)

Hardens the G14 non-mineralised check by testing whether anomalous concentrations are
spatially controlled by a known contamination source or proximity covariate — a
pattern consistent with anthropogenic dispersion (smelter plume, fluvial dispersion,
road dust) rather than in-situ mineralisation. [src: V13/Exploration Geochemistry; ref: Reimann et al. 2008]

**`--contam-coords "E,N"`** — provide a known source point (smelter, waste dump, road
intersection) in the same projection as `--coords`. For each `--elements` element the
script computes Euclidean distance from each sample to the source, then
`scipy.stats.spearmanr(concentration, distance)`. An element is **FLAGGED** when
`rho ≤ −0.5` AND `p < 0.05` (concentration systematically decreases with distance →
consistent with a dispersion plume from the source). Requires `--coords`.

**`--contam-covariate <col>`** — the name of an existing proximity column already
in the CSV (e.g. `dist_river`, `dist_road`, pre-computed Euclidean distance). For
each element: `spearmanr(concentration, covariate)`. **FLAGGED** when `|rho| ≥ 0.5`
AND `p < 0.05` (strong spatial control — the agent interprets sign/direction for
context). The covariate column must be present in the input CSV.

Both flags can be given together (`mode = "coords+covariate"`); an element is flagged
if either basis independently flags it.

**Minimum pairs:** if fewer than 5 non-NaN pairs exist for an element, the test is
skipped and `flag = false`.

**Output** (`summary["contamination_screen"]`):

```json
{
  "mode": "coords",
  "source_coords": [0.0, 0.0],
  "per_element": {
    "Cu_ppm": {"spearman_rho": -0.94, "p_value": 1.2e-35, "flag": true,
               "basis": "distance_from_source"},
    "Zr_ppm": {"spearman_rho": 0.04,  "p_value": 0.72,    "flag": false,
               "basis": "distance_from_source"}
  },
  "n_flagged": 1, "n_elements": 2,
  "assessment": "1/2 elements strongly spatially controlled by source(0,0) — anomalies may be dispersion/contamination, not in-situ mineralisation (G14)"
}
```

If `n_flagged ≥ ⌈n_elements / 2⌉`, a warning phrase is appended to
`multi_element.note` to surface in Section 5 (Abbas Gate) non-mineralised reasoning.

If neither flag is given, the screen is silently skipped and
`contamination_screen` is absent from the summary — no change to existing behaviour.

## Multi-element (compositional) anomalies — G11 ORDER IS MANDATORY
1. Log-ratio transform first (**ILR**, full rank) — never raw ppm (closure; see compositional-data.md).
2. **MCD robust covariance** — classic covariance is masked by outliers. [ref: Filzmoser & Hron 2009; Reimann et al. 2008]
3. **Robust Mahalanobis** on ILR coords flags multivariate outliers (true associations, not single spikes).
   Composition auto-includes an immobile anchor so co-mobile pathfinder haloes stay detectable. [implemented: anomaly.py]
- **n≫p stability guard** — MCD needs n ≫ p (p = d−1 ILR dims). If `n/p < 5`, MCD covariance is unreliable:
  the script reports `multi_element.n_over_p` and `note="low n/p…"`, and falls back to classic Mahalanobis
  if MCD cannot fit. Do NOT trust a robust Mahalanobis when n/p is small — degrade to pairwise log-ratio /
  CLR biplot screening. [implemented: anomaly.py]
