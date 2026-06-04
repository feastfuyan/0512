---
name: geochemistry
description: Use for geochemistry interpretation, exploration geochemistry, anomaly detection, pathfinder vectoring, REE/trace-element normalization, isotope tracing, QAQC of assay data, and turning geochemical data into ML features. Routes to deterministic scripts (no LLM arithmetic) and textbook-grounded cards. Triggers — 地球化学, 勘查地化, 异常识别, pathfinder, REE 配分, 归一化, QAQC, CoDA, 成分数据, 同位素示踪, 地化特征工程, geochemical anomaly, background threshold, C-A fractal.
---

# Geochemistry (凌云 · 首席地球化学家工具集)

Textbook-grounded geochemistry. **The LLM never does the arithmetic** — it routes data to `scripts/` and interprets results with `references/` cards, always citing sources (G7/G21), respecting compositional closure (G11) and anomaly≠resource (G14).

## Reference set follows the sample MEDIUM (do not default)
Rock/igneous → chondrite (SM89). Soil/stream-sediment/water → PAAS or UCC. Unknown medium → ASK. See `references/normalization.md`.

## When to use which card
- `references/pathfinders.md` — deposit→pathfinder elements, diagnostic ratios, mobility, scoring weights (orogenic_gold/porphyry_cu/vms/iocg/li_pegmatite/epithermal_au), NON-mineralized causes (anti over-call, G14).
- `references/normalization.md` — pinned SM89/PAAS values + Eu*/Ce* (geometric + neighbour-fallback) + ratios.
- `references/anomaly-methods.md` — robust thresholds, MAD=0 fallback, C–A/S–A fractal, spatial local background (+ anomalous-core caveat), immobile-element background, ILR→MCD robust Mahalanobis (+ n≫p guard).
- `references/qaqc.md` — blank/duplicate/CRM, variance components, Thompson-Howarth, censoring.
- `references/compositional-data.md` — closure, CLR/ILR, zero replacement, anti-leakage.

## When to run which script (deterministic; parse the JSON summary)
Order: **geochem_qc → (normalize | compositional → anomaly) → feature_engineer**.
> 脚本在技能目录的 `scripts/` 下；调用用绝对路径 `python "$(dirname "$0"/../skills/lynai-geochemistry/scripts/<name>.py)"` 或直接用 `~/.openclaw/workspace/skills/lynai-geochemistry/scripts/<name>.py`。
- `scripts/geochem_qc.py` — ALWAYS FIRST. Unit harmonization + isotope-safe ND + QC thresholds. `qc_summary.pass==false` → STOP.
- `scripts/normalize.py` — REE normalization (`--ref` chosen by medium) + Eu*/Ce*.
- `scripts/compositional.py` — CLR/ILR log-ratios.
- `scripts/anomaly.py` — single robust thresholds, KNN spatial local background, ILR→MCD multi-element Mahalanobis (auto immobile anchor; `multi_element.n_over_p` + `note`), pathfinder score.
- `scripts/feature_engineer.py` — frozen IO skeleton for ML (Phase-4 maturity).

## When to query gbrain (cite to §/page)
`gbrain query "pathfinder elements for <deposit> mobility dispersion" --no-expand` · `"<element> anomaly non-mineralized causes scavenging" --no-expand` · `"REE normalization Eu anomaly <deposit>" --no-expand`

## Guardrails
G11 closure (multivariate ⇒ ILR first) · G14 anomaly ≠ resource · G7/G21 every number cited · QAQC hard gate · censored method stated · reference set follows medium.
