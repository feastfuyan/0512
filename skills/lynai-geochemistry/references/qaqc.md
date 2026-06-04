# QAQC of Geochemical / Assay Data

> Machine-executable thresholds live in `config.yaml` (single source of truth), enforced by
> `scripts/geochem_qc.py`. This card explains what each control measures and how to read failures.

## Numerical thresholds (config.yaml `qc:`)
Blank < 2 × DL (contamination) · CRM recovery 0.85–1.15 (accuracy) · duplicate RPD < 20% (precision) ·
batch drift < 2σ (stability). Any fail → `qc_summary.pass=false` → agent STOPS, reports `failed_rules`. [src: V13/Exploration Geochemistry]

## Variance components (which duplicate measures what)
Field duplicate = sampling + sub-sampling + analytical (total) · pulp/coarse-reject duplicate =
sub-sampling + analytical · analytical replicate = analytical only. Partitioning these locates where
to invest (sampling protocol vs lab). [ref: Garrett 1969; standard QAQC]

## Precision estimation
**Thompson-Howarth** — precision is concentration-dependent: sₐ ≈ s₀ + k·c. Plot |dup₁−dup₂| vs mean;
set control limits at the target precision. Prefer this to a single global RPD. [ref: Thompson & Howarth 1978]

## Detection limits & method suitability
ICP-MS/OES (multi-element, low DL), AAS, pXRF (field; matrix effects), **fire assay** for Au, INAA.
Match method DL to deposit tenor. Below-DL handling: ROS default (anomaly-methods.md). [src: V13/Exploration Geochemistry; ref: Helsel 2012]
