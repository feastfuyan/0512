# REE / Trace-Element Normalization (pinned reference sets)

> Pinned, version-tagged values + exact formulas used by `scripts/normalize.py`. Reference set
> follows the sample MEDIUM. Never mix reference sets within one study.

## Which reference for what (MEDIUM-driven)
- **CI chondrite** → igneous rocks, mantle/melt processes. Default = **Sun & McDonough 1989 (SM89_v1)**. [ref: Sun & McDonough 1989]
- **PAAS / NASC** → soils, stream sediments, sedimentary-hosted systems, natural waters. PAAS = Taylor & McLennan 1985. [ref: Taylor & McLennan 1985]
- **UCC** → upper-crustal background for surface media. [ref: Rudnick & Gao 2003]
- **Primitive Mantle** → incompatible-element spider diagrams. [src: Henderson, REE Geochemistry]
> ⚠️ Two value sets circulate under "SM89"; we lock the self-consistent A-set (Yb 0.170 / Lu 0.0254, Yb/Lu≈6.69). When comparing to a published pattern, FIRST confirm which reference set the source used. [ref: SM89 vs McDonough & Sun 1995]

## CI chondrite values, ppm (Sun & McDonough 1989; pinned, A-set)
La 0.237 · Ce 0.612 · Pr 0.095 · Nd 0.467 · Sm 0.153 · Eu 0.058 · Gd 0.2055 · Tb 0.0374 ·
Dy 0.254 · Ho 0.0566 · Er 0.1655 · Tm 0.0255 · Yb 0.170 · Lu 0.0254. REE order excludes Pm. [ref: Sun & McDonough 1989]

## PAAS values, ppm (Taylor & McLennan 1985; pinned)
La 38.2 · Ce 79.6 · Pr 8.83 · Nd 33.9 · Sm 5.55 · Eu 1.08 · Gd 4.66 · Tb 0.774 · Dy 4.68 ·
Ho 0.991 · Er 2.85 · Tm 0.405 · Yb 2.82 · Lu 0.433. [ref: Taylor & McLennan 1985]

## Exact formulas (xₙ = x_sample / x_reference)
- `Eu/Eu*` = Euₙ / √(Smₙ · Gdₙ)  (geometric-mean of neighbours)
- `Eu/Eu*` fallback (Gd missing/<DL) = Euₙ / (0.67·Smₙ + 0.33·Tbₙ)  [ref: Taylor & McLennan 1985]
- `Ce/Ce*` = Ceₙ / √(Laₙ · Prₙ)
- `Ce/Ce*` fallback (Pr missing/<DL) = Ceₙ / (0.5·Laₙ + 0.5·Ndₙ)
- `(La/Yb)ₙ` overall slope · `(La/Sm)ₙ` LREE slope · `(Gd/Yb)ₙ` HREE slope

The `√(Sm · Gd)` geometric-mean formula is the standard for `Eu/Eu*` interpolation. [ref: Sun & McDonough 1989]

## Caveats the agent must respect
- **Ce anomaly disambiguation (seawater/weathering)** — a true positive `La` anomaly can masquerade as a `Ce` anomaly; cross-check `Ce/Ce*` against `Pr/Pr*`. [ref: Bau & Dulski 1996]
- **Tetrad / non-CHARAC behaviour** — highly fractionated granites/pegmatites (your LCT systems) show REE tetrad effects that distort the geometric-mean `Eu*` assumption; flag for LCT REE interpretation. [ref: Bau 1996]
- **Slope interference** — extreme LREE/HREE fractionation biases the neighbour interpolation; prefer measured Gd/Pr over the fallback when available.

## Interpretation hooks
Steep LREE-enriched + negative Eu → evolved felsic/granitoid; flat HREE + positive Eu → plagioclase cumulate; strong negative Ce → oxidative marine/weathering overprint. [src: Henderson, REE Geochemistry]
