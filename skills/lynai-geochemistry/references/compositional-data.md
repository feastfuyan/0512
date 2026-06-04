# Compositional Data Analysis (CoDA) — why raw ppm lies

> First-principles guardrail (G11). Geochemical concentrations carry only RELATIVE information;
> naive statistics on raw ppm are invalid.

## The problem
Even trace-element ppm (which do not literally sum to 10⁶) carry only relative information — any
sub-composition must be analysed via log-ratios. Treating them as free real numbers induces **spurious
negative correlations** and **singular covariance**, so correlation, PCA, and Mahalanobis on raw ppm are
biased/meaningless. [ref: Aitchison 1986; Filzmoser, Hron & Reimann 2009/2018]

## The fix: log-ratio transforms
- **ALR** — log(xᵢ/x_D); denominator arbitrary.
- **CLR** — log xᵢ − mean(log x); symmetric but **rank-deficient** (rows sum to 0, singular cov). Good for biplots. [implemented: coda.clr]
- **ILR** — orthonormal basis (sequential binary partition / balances); **full rank**, isometric to CLR for
  Aitchison distance. Use for Mahalanobis/ML. Default basis = standard SBP. [implemented: coda.ilr; ref: Egozcue & Pawlowsky-Glahn 2003]
- **ILR basis interpretability** — Mahalanobis/anomaly results are basis-invariant (good), BUT if you
  interpret an INDIVIDUAL ILR coordinate, the basis (balances) must be geochemically meaningful (e.g.
  mobile-vs-immobile, pathfinder-group-vs-rock-forming). Do not over-read a "standard SBP" coordinate.

## Zero / below-DL handling in CoDA
log-ratios are undefined at zero → **multiplicative replacement** (preserves ratios), δ = 0.65 × column min.
[implemented: coda.multiplicative_replacement; ref: Martín-Fernández et al. 2003]. High censoring → model-based
**lrEM / lrDA** (zCompositions). [ref: Palarea-Albaladejo & Martín-Fernández 2015]

## Anti-leakage for ML features
Do NOT concatenate raw ppm AND their CLR/ILR — it re-introduces closure and collinearity, breaking
linear/tree models. `feature_engineer.py` tags raw columns non-model. [implemented: feature_engineer.py]

## Multivariate outlier detection
Robust (MCD) Mahalanobis on ILR coordinates, subject to the n≫p guard (anomaly-methods.md). [ref: Filzmoser & Hron 2009]
