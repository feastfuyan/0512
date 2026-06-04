# Pathfinder Elements, Diagnostic Ratios, Mobility & Scoring

> Deposit→indicator associations (with diagnostic ratios), weathering mobility, the pathfinder
> scoring weights used by `scripts/anomaly.py` (single source of truth = `geochemlib/pathfinder.py`),
> and the NON-mineralized causes of anomalies (anti over-call, G14).

## Deposit-type pathfinder associations
| Deposit type | Core | Pathfinder halo (dispersed) | Diagnostic ratio / note | [src] |
|---|---|---|---|---|
| Orogenic Au | Au | As, Sb, Bi, Te, W, Hg, Mo, Ag, B (±Se, Tl) | As-Sb enter first (distal); Bi-Te-W index high-T/proximal; **B = tourmaline alteration (near-ore)** | [src: V13/Geochemistry of Hydrothermal Gold] |
| Epithermal Au-Ag (LS) | Au, Ag | As, Sb, Hg, Tl, Se (±Ba, Mn, base metals at depth) | Hg-Tl shallow; base metals deepen | [src: V13/Geochemistry of Hydrothermal Gold] |
| Epithermal Au-Ag (HS) | Au, Cu | As, Sb, Bi, Te, Sn, Mo, W (±Hg) | advanced-argillic; Cu-Bi-Te-Sn-Mo distinguishes from LS | [src: V13/Geochemistry of Hydrothermal Gold] |
| Porphyry Cu(-Mo-Au) | Cu, Mo, Au | distal As, Sb, Hg, Tl, Mn, Pb, Zn, (Re, Se proximal) | zoned; **pyrite/sericite trace-element vectoring** (Halley/Cooke); Mn-As-Sb-Tl = distal shell | [src: V13/Geochemistry of Porphyry Deposits] |
| VMS | Cu, Zn, Pb | Ba, Tl, Hg, As, Sb, Mn, Cd, (Au, Ag, In, Se) | **Mn = most distal exhalite halo**; Cd in sphalerite | [src: V13/Volcanogenic Massive Sulfide Deposits] |
| IOCG (-Cu-Au-REE-P-Ag-U-Co) | Cu, Au, Fe | REE, P, Co, U, Ag, F, Bi, Ni, (Mo, Ba) | LREE + P + F + magnetite/hematite assoc. | [src: V13/Iron Oxide(-Cu-Au-REE-P-Ag-U-Co) Systems] |
| Sediment-hosted Cu | Cu | Ag, Co, (Zn, Pb, Mo, U) | redbed/reduced-facies redox boundary | [src: V13/Low-Temperature Sediment-Hosted Copper Deposits] |
| SEDEX / MVT Zn-Pb | Zn, Pb | Ba, Tl, As, Sb, Hg, Cd, Ag, F (±Ge, In) | Tl-As-Sb-Hg + Ba (SEDEX exhalite) | [ref: Leach et al. 2005] |
| LCT pegmatite (Li) | Li, Cs, Ta | Rb, Be, Sn, B, F, Nb, Ga, Tl | **K/Rb < 30 = extreme fractionation; Nb/Ta ↓ toward Ta ore; Mg/Li in micas** (use RATIOS, see caveat) | [ref: London 2008; Černý et al. 2005] |
| U sandstone (roll-front) | U | Se, Mo, V, Re, As | redox-front zoned (oxidized→reduced) | [src: V13/Uranium Ore Deposits] |
| U unconformity | U | Ni, Co, As, Pb, B, REE (±Au, Pt, Cu) | clay-alteration controlled; radiogenic Pb | [src: V13/Uranium Ore Deposits] |
| Sedimentary Mn | Mn | Fe, Ba, Sr, Co, Ni, Cu, Zn | **Mn/Fe > 10; Ba-Co = hydrothermal pulse** | [ref: Roy 1997; Maynard, Sedimentary Ore Deposits] |
| REE-Nb-Ta (carbonatite/alkaline) | REE, Nb, Ta | Zr, Hf, Th, F, P, Ba, Sr | LREE-enriched; F-P-Ba-Sr | [src: V13/Geochemistry of the REE, Nb, Ta, Hf, and Zr Deposits] |

## Weathering / supergene mobility (controls sample-medium & dispersion distance)
| Mobility | Elements | Note |
|---|---|---|
| High | Mo, U, Se, As(ox), Sb, Zn, Cu(ox), B, Re, **Cd, F, Hg(vapour), Li, Rb, Cs** | hydromorphic; broad haloes; alkali metals key for Li vectoring |
| Moderate | Au(as Cl/HS complexes), Ag, Co, Ni, Bi | Eh-pH/ligand dependent |
| Low / immobile | Zr, Ti, Al, Th, Nb, Ta, Hf, Cr, REE, Sn, **Pb** | residual; good background anchors. **Pb is LOW** (strong adsorption, insoluble sulfate/carbonate/phosphate). **W**: tungstate moderately mobile in oxidizing-alkaline conditions — not strictly immobile. **Ce⁴⁺ decoupled** (immobile under oxidation) → drives Ce/Ce* (see normalization.md). | [ref: Reimann et al. 2008; Rose, Hawkes & Webb 1979] |

## Pathfinder scoring weights (MUST equal `geochemlib/pathfinder.py`)
`pathfinder_score = Σ wᵢ · normalized_anomalyᵢ` (renormalized over PRESENT elements; report which were measured).
| System (`--pathfinder`) | Weights |
|---|---|
| `orogenic_gold` | As 0.30, Sb 0.25, Bi 0.20, Te 0.15, W 0.10 |
| `porphyry_cu` | Mo 0.30, Au 0.20, Pb 0.15, Zn 0.15, As 0.10, Sb 0.10 |
| `vms` | Zn 0.30, Pb 0.25, Ba 0.20, Tl 0.15, Hg 0.10 |
| `iocg` | Cu 0.25, Co 0.20, U 0.15, La 0.10, Ce 0.10, P 0.10, F 0.10 |
| `li_pegmatite` | Cs 0.30, Rb 0.20, Ta 0.15, Sn 0.15, Be 0.10, Nb 0.10 |
| `epithermal_au` | As 0.25, Sb 0.20, Hg 0.20, Tl 0.15, Se 0.10, Ag 0.10 |

**Caveats:** `orogenic_gold` deliberately EXCLUDES Au — it is a **halo/vectoring score**, separate from the Au anomaly itself (do not conflate). `li_pegmatite` single-element weighting is a **coarse screen only**; the real LCT vectors are fractionation RATIOS (K/Rb, K/Cs, Nb/Ta, Mg/Li) — compute those separately. `renormalize=True` rescales over measured elements, so always report which pathfinder elements were actually analysed (a package missing Re/Se/Te changes the score meaning).

## NON-mineralized causes of anomalies (anti over-call, G14) — with diagnostic indicators
The agent MUST force these checks before calling an anomaly prospective: [src: V13/Exploration Geochemistry]
1. **Black-shale / organic-matter false highs** — *check*: co-spike of Mo+U+V+Ni+As+Cu+Zn+Cr. *action*: regress against an immobile lithological proxy (Al or Ti) in ILR space; if the anomaly vanishes → tag **"lithological background (organic shale)"**, not mineralization.
2. **Fe-Mn oxide/hydroxide scavenging** — *check*: strong positive correlation of Fe/Mn with base metals (Co, Ni, Cu, Zn, Pb, As). *action*: if single-element highs strictly track the Mn-Fe matrix → tag **"secondary scavenging (supergene)"**.
3. **Mafic vs felsic lithological contrast** — *check*: high Cr+Ni+Co mimicking targets. *action*: check Mg/Al or Ti/Zr; true magmatic anomalies separate from regional baseline lithology.
4. **Nugget effect (Au)** — coarse free-gold spot highs uncorrelated with a coherent halo; the #1 false anomaly in Au exploration. Cross-check As-Sb-Bi halo continuity before trusting a lone Au spike.
5. **Heavy-mineral / resistate mechanical concentration** — monazite/zircon/cassiterite placer enrichment → false REE/Th/Zr/Sn anomalies; check for hydraulic sorting (grain size, immobile-element coherence).
6. **Laterite / ferricrete scavenging** — tropical weathering-crust adsorption (broad multi-element highs in residual profiles).
7. **Anthropogenic contamination** — Pb, Zn, Cu, Hg near roads/mines/agriculture.
8. **Clastic dilution / grain-size / sample-medium** — normalize against an immobile element to correct.
