"""
figure_lint.py — Gate-by-construction lint layer for miningclaw-figure.

SCOPE — DETERMINISTIC FLOOR ONLY
---------------------------------
``lint_product`` pre-certifies the deterministic floor dims (readability, labeling,
data_viz_integrity, layout_integrity, aesthetic_consistency) by running the VENDORED
product figure-quality scorers from ``vendored.figure_checks_vendored`` on the rendered
SVG string.

IMPORTANT BOUNDARY (C2 / architectural constraint):
  The product's perceptual dims (readability / aesthetic_consistency) require its
  Playwright + Claude Opus vision judge for full evaluation and are NOT substitutable
  by this linter.  A ``lint_product`` green means the figure clears the deterministic
  floor of all 5 dims at QUALITY_FLOOR (9.0); it does NOT guarantee a passing vision
  judge score.  Both gates must pass before a figure ships.

Guard summary
-------------
* G14 (fail-closed): if ``is_economic`` AND ``classification in {"inferred","exploration-target"}``
  AND NOT ``has_inferred_exclusion`` → ``data_viz_integrity`` floored to 0.0,
  blocker ``"G14: inferred/exploration-target in economic figure"`` added, ``passed=False``.
* I8:  axis/encoding title must carry a unit/currency token; stub for horizontal-bar v1
  (real/nominal + zero-baseline checks deferred to Phase 2 per spec comment).
* I7:  risk-palette check (when chart_kind == "risk-matrix" — not reachable in v1 product
  path; guard is present so future chart types don't silently bypass).
* I11: ``chart_kind == "line-combo"`` → out-of-scope blocker, fail-closed (line-combo is
  not a registered product chart type in v1; this guard is defensive for future drift).
"""

from __future__ import annotations

import re
import sys
import pathlib
from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Ensure vendored module is importable; product module is optional (try/except below)
# ---------------------------------------------------------------------------
_SK = pathlib.Path(__file__).parent
if str(_SK) not in sys.path:
    sys.path.insert(0, str(_SK))

import vendored.figure_checks_vendored as _ven  # noqa: E402

try:
    from report_service.runtime.quality.rubric import FIGURE_DIMENSIONS, QUALITY_FLOOR
except ImportError:  # pragma: no cover — product missing; fall back to known values
    FIGURE_DIMENSIONS = (
        "readability", "labeling", "data_viz_integrity",
        "layout_integrity", "aesthetic_consistency",
    )
    QUALITY_FLOOR = 9.0

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class LintResult:
    """Output of lint_product / lint_paper.

    Attributes:
        passed:     True iff no dim is below QUALITY_FLOOR and blockers is empty.
        dim_scores: dict mapping each FIGURE_DIMENSIONS key → float score.
        blockers:   list of human-readable blocker strings (empty when passed).
    """
    passed: bool
    dim_scores: dict
    blockers: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Unit/currency token pattern: matches recognised unit strings or currency symbols.
# Deliberately does NOT match arbitrary alpha text — only known tokens or symbols.
_UNIT_RE = re.compile(
    r'(?:'
    r'[%$€£¥₩]'                                                          # currency/percent symbols
    r'|(?<!\w)(?:'
    r'tenements?|tonnes?|oz|Mt|Moz|km²?|m²|ha|koz|ktpa|Mtpa|ktCO2'      # common mining units
    r'|USD|AUD|CAD|GBP|EUR|ZAR|CNY|JPY'                                  # currency codes
    r'|m\b|t\b|g/t|%\b|ppm|ppb'                                          # other common units
    r')(?!\w)'
    r')',
    re.IGNORECASE,
)

_G14_CLASSIFICATIONS: frozenset[str] = frozenset({"inferred", "exploration-target"})


def _check_i8_unit(svg_text: str, expected_unit: str | None = None) -> bool:
    """Return True if the SVG text content carries at least one unit/currency token.

    Scans all <text>…</text> content in the rendered SVG for a detectable
    unit or currency token (e.g. "Mt", "%", "$", "tenements", "oz").

    Parameters
    ----------
    svg_text : str
        The rendered SVG string to scan.
    expected_unit : str | None
        If provided (non-empty string), verifies that this exact unit token
        appears in the SVG text (robust path for exotic units not in curated list).
        If None, falls back to the curated _UNIT_RE pattern detection.

    Returns
    -------
    bool
        True if the expected unit is found (when provided) or if at least one
        curated unit/currency token is detected (when expected_unit is None).

    Phase 2 note: real/nominal label and zero-baseline checks are stubbed here
    for horizontal-bar v1.  Full per-type enforcement lands when Phase 2 chart
    types are exercised (spec §I8).
    """
    text_contents = re.findall(r'<text[^>]*>(.*?)</text>', svg_text, re.IGNORECASE | re.DOTALL)
    combined = " ".join(text_contents)

    # Robust path: if expected_unit is provided, check for exact match
    if expected_unit:
        return expected_unit in combined

    # Fallback: use curated token list
    return bool(_UNIT_RE.search(combined))


def _apply_i8_unit_guard(
    svg: str,
    scores: dict,
    blockers: list[str],
    *,
    expected_unit: str | None = None,
) -> None:
    """Mutate scores/blockers in-place for the I8 unit-missing guard.

    When NO unit/currency token is detectable in the SVG text content, the
    labeling dim is floored below QUALITY_FLOOR and a blocker is added.

    Parameters
    ----------
    svg : str
        The rendered SVG string.
    scores : dict
        Dimension scores dict (mutated in-place if unit check fails).
    blockers : list[str]
        Blockers list (mutated in-place if unit check fails).
    expected_unit : str | None
        Optional expected unit token. If provided, checks for this exact string
        in the SVG text instead of using the curated pattern list. Enables
        exotic units (e.g. 'bbl', 'koz', 'dwt', 'Mlb') to pass the gate.

    Phase 2 note: real/nominal + zero-baseline checks remain stubs;
    only the token-presence check is active in v1.
    """
    if not _check_i8_unit(svg, expected_unit=expected_unit):
        scores["labeling"] = min(scores.get("labeling", QUALITY_FLOOR), QUALITY_FLOOR - 1.0)
        blockers.append(
            "I8: no unit/currency token detected in SVG text labels — "
            "value-axis labels must carry a unit (e.g. 'Mt', '%', '$', 'tenements') "
            "for self-sufficient readability; real/nominal + zero-baseline checks are Phase-2 stubs"
        )


def _apply_g14_guard(
    scores: dict,
    blockers: list[str],
    *,
    is_economic: bool,
    classification: str,
    has_inferred_exclusion: bool,
) -> None:
    """Mutate scores/blockers in-place for the G14 inferred-in-economic guard."""
    if (
        is_economic
        and classification.lower() in _G14_CLASSIFICATIONS
        and not has_inferred_exclusion
    ):
        scores["data_viz_integrity"] = 0.0
        blockers.append(
            "G14: inferred/exploration-target in economic figure — "
            "exclude Inferred from production/cashflow charts or add explicit exclusion note"
        )


def _apply_i11_guard(fig: "_ven.Figure", blockers: list[str]) -> None:
    """I11: flag line-combo as out-of-scope (not a v1 product chart type)."""
    if fig.chart_kind == "line-combo":
        blockers.append(
            "I11: line-combo chart kind is out-of-scope for the product path in v1 — "
            "use paper render target or wait for Phase 2 product adoption"
        )


def _apply_i7_guard(fig: "_ven.Figure", blockers: list[str]) -> None:
    """I7: risk-palette check (risk-matrix not reachable in v1 product path; guard is defensive)."""
    if fig.chart_kind == "risk-matrix":
        # In future: validate fill colours are in the approved risk palette.
        # For v1 this chart kind is not reachable via the product path.
        blockers.append(
            "I7: risk-matrix chart kind requires risk-palette colour validation — "
            "not implemented in v1 product path"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lint_product(
    svg: str,
    *,
    is_economic: bool = False,
    has_inferred_exclusion: bool = False,
    classification: str = "n/a",
    expected_unit: str | None = None,
) -> LintResult:
    """Lint a product-path SVG string against the deterministic quality floor.

    Parameters
    ----------
    svg:
        The rendered HTML/SVG string (typically the output of render_product_svg).
    is_economic:
        True when the figure appears in an economic section (cashflow, production
        profile, NPV sensitivity, etc.) where G14 applies.
    has_inferred_exclusion:
        True when the figure or its surrounding report explicitly states that
        Inferred resources are excluded from the economic model.  When True,
        the G14 guard is bypassed.
    classification:
        The JORC/NI-43-101 resource classification of the underlying data.
        Values that trigger the G14 guard: ``"inferred"`` or
        ``"exploration-target"`` (case-insensitive).
    expected_unit:
        Optional expected unit token (e.g. "bbl", "koz", "dwt", "Mlb").
        If provided, the I8 check validates that this exact string appears
        in the SVG text labels. This enables exotic mining units not in the
        curated _UNIT_RE list to pass the gate. If None, falls back to
        curated pattern detection (unchanged behavior).

    Returns
    -------
    LintResult
        ``passed`` is True iff no dim score is below QUALITY_FLOOR and
        blockers is empty.

    Notes
    -----
    * Deterministic floor only — perceptual dims require the Playwright+Opus
      vision judge; a green here does NOT mean the figure passes vision review.
    * If the SVG contains zero chart-block figures (e.g. mc-08 ``<div class="card">``
      wrappers), ``dim_scores`` reflects the floor defaults for a zero-figure input
      and ``passed`` is True (empty input = nothing to fail; the caller decides
      whether zero figures is a problem for their context).
    * I8 real/nominal and zero-baseline sub-checks are stubbed for horizontal-bar v1
      (per spec §I8 Phase 2 note).
    """
    blockers: list[str] = []

    # --- Extract figures via vendored scorer ---
    figures = _ven.extract_figures(svg)

    if not figures:
        # No chart-block found (e.g. mc-08 card wrapper) — return floor, no blockers.
        scores = {d: QUALITY_FLOOR for d in FIGURE_DIMENSIONS}
        return LintResult(passed=True, dim_scores=scores, blockers=[])

    # --- Score the first (and in v1, only expected) figure ---
    # detect_duplicate_geometry uses the full list; v1 corpus is single-figure
    duplicate_indices = _ven.detect_duplicate_geometry(figures)

    aggregated: dict[str, float] = {d: QUALITY_FLOOR for d in FIGURE_DIMENSIONS}

    for idx, fig in enumerate(figures):
        is_duplicate = idx in duplicate_indices
        scores = _ven.score_figure_deterministic(fig, is_duplicate=is_duplicate)

        # Merge: take the min across figures so any floor propagates
        for dim in FIGURE_DIMENSIONS:
            aggregated[dim] = min(aggregated[dim], scores.get(dim, QUALITY_FLOOR))

        # Per-figure structural guards
        _apply_i11_guard(fig, blockers)
        _apply_i7_guard(fig, blockers)

    # --- G14 guard (applied to merged scores) ---
    _apply_g14_guard(
        aggregated,
        blockers,
        is_economic=is_economic,
        classification=classification,
        has_inferred_exclusion=has_inferred_exclusion,
    )

    # --- I8 unit check (applied to merged scores) ---
    _apply_i8_unit_guard(svg, aggregated, blockers, expected_unit=expected_unit)

    # --- Determine pass/fail ---
    floor_fail = [
        d for d, v in aggregated.items() if v < QUALITY_FLOOR
    ]
    for dim in floor_fail:
        if not any(dim in b for b in blockers):
            blockers.append(
                f"dim '{dim}' scored {aggregated[dim]:.1f} < floor {QUALITY_FLOOR}"
            )

    passed = not blockers

    return LintResult(passed=passed, dim_scores=aggregated, blockers=blockers)



# ---------------------------------------------------------------------------
# Paper-path lint
# ---------------------------------------------------------------------------

# Risk-semantic palette — the four approved hex codes (I7).
# A paper-path SVG with color_scale=="risk-semantic" must contain at least one.
_RISK_HEX: frozenset[str] = frozenset({
    "#C00000",   # CRITICAL
    "#E36C09",   # HIGH
    "#F2C500",   # MEDIUM
    "#4F7942",   # LOW
})
_RISK_HEX_RE = re.compile(
    r'#(?:C00000|E36C09|F2C500|4F7942)',
    re.IGNORECASE,
)


def lint_paper(
    svg: str,
    fs,  # FigureSpec | None  — typed loosely to avoid circular import at module level
) -> LintResult:
    """Light paper-path lint.

    Checks (no product gate applied):
    (a) claim present — if ``fs`` is None or ``fs.claim`` is empty → blocker.
    (b) axis/labeling present — at least one ``<text>`` element in the SVG.
    (c) no gross viewBox overflow estimate — text ``x`` / ``y`` attributes stay
        within the declared viewBox width/height when those are parseable.
    (d) risk-palette check — if ``fs`` is provided and
        ``fs.paper.color_scale == "risk-semantic"``, the SVG must contain at
        least one of the approved risk hex codes.

    Parameters
    ----------
    svg:
        The rendered paper-path SVG string.
    fs:
        A :class:`FigureSpec` with ``render_target="paper"``, or ``None``.
        Passing ``None`` is treated as a missing claim (blocker).

    Returns
    -------
    LintResult
        ``passed`` is True iff no blockers were raised.
    """
    blockers: list[str] = []

    # (a) Claim check
    claim = None
    if fs is None:
        blockers.append(
            "claim missing: FigureSpec not provided (fs=None) — "
            "a non-empty claim is required on all paper-path figures"
        )
    else:
        claim_val = getattr(fs, "claim", None)
        if not claim_val or not claim_val.strip():
            blockers.append(
                "claim missing: FigureSpec.claim is empty — "
                "a non-empty claim is required on all paper-path figures"
            )
        else:
            claim = claim_val

    # (b) Labeling check — at least one <text> element
    if not re.search(r'<text\b', svg, re.IGNORECASE):
        blockers.append(
            "labeling: no <text> elements found in paper SVG — "
            "axis titles and tick labels must be present for self-sufficient rendering"
        )

    # (c) Gross viewBox overflow estimate
    # Parse declared viewBox dimensions
    vb_match = re.search(r'viewBox\s*=\s*["\']?\s*[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)', svg)
    if vb_match:
        vb_w = float(vb_match.group(1))
        vb_h = float(vb_match.group(2))
        # Check text x attributes
        for m in re.finditer(r'<text[^>]*\bx="([\d.]+)"', svg, re.IGNORECASE):
            tx = float(m.group(1))
            if tx > vb_w * 1.05:  # 5 % tolerance
                blockers.append(
                    f"layout: text x={tx:.0f} exceeds viewBox width {vb_w:.0f} "
                    f"(>5% tolerance) — possible overflow in paper SVG"
                )
                break
        for m in re.finditer(r'<text[^>]*\by="([\d.]+)"', svg, re.IGNORECASE):
            ty = float(m.group(1))
            if ty > vb_h * 1.05:
                blockers.append(
                    f"layout: text y={ty:.0f} exceeds viewBox height {vb_h:.0f} "
                    f"(>5% tolerance) — possible overflow in paper SVG"
                )
                break

    # (d) Risk-palette check
    if fs is not None:
        # Support both new (fs.opts) and deprecated legacy (fs.paper) access
        _opts = getattr(fs, "opts", None) or getattr(fs, "paper", None)
        if _opts is not None and getattr(_opts, "color_scale", "default") == "risk-semantic":
            if not _RISK_HEX_RE.search(svg):
                blockers.append(
                    "risk-palette: color_scale='risk-semantic' is set but none of the "
                    "approved risk hex codes (#C00000 CRITICAL / #E36C09 HIGH / "
                    "#F2C500 MEDIUM / #4F7942 LOW) were found in the SVG — "
                    "apply the risk-semantic palette or correct color_scale"
                )

    passed = not blockers
    # Paper lint does not produce dim_scores; return an empty dict (no product gate)
    return LintResult(passed=passed, dim_scores={}, blockers=blockers)


def lint_figure(
    svg: str,
    fs,  # FigureSpec
    *,
    expected_unit: str | None = None,
) -> LintResult:
    """Unified lint entry point. Applies all guards regardless of document type.

    Runs:
    - claim check (claim must be non-empty)
    - I8 unit token check
    - G14 inferred-in-economic guard (via fs.opts)
    - risk-palette check when color_scale=="risk-semantic"
    - deterministic floor checks when output_format=="html-embed" (vendored scorer)

    Parameters
    ----------
    svg:
        The rendered SVG or HTML string.
    fs:
        The FigureSpec used to produce the SVG.
    expected_unit:
        Optional unit token for exotic units not in the curated list (see lint_product).
    """
    blockers: list[str] = []

    # (a) Claim check
    claim_val = getattr(fs, "claim", None)
    if not claim_val or not claim_val.strip():
        blockers.append(
            "claim missing: FigureSpec.claim is empty — "
            "a non-empty claim is required on all figures"
        )

    opts = getattr(fs, "opts", None)

    # (b) G14 guard
    is_economic = getattr(opts, "is_economic_figure", False) if opts else False
    classification = getattr(opts, "classification_category", "n/a") if opts else "n/a"
    scores: dict = {d: QUALITY_FLOOR for d in FIGURE_DIMENSIONS}
    _apply_g14_guard(
        scores, blockers,
        is_economic=is_economic,
        classification=classification,
        has_inferred_exclusion=False,
    )

    # (c) I8 unit check
    _apply_i8_unit_guard(svg, scores, blockers, expected_unit=expected_unit)

    # (d) Risk-palette check
    color_scale = getattr(opts, "color_scale", "default") if opts else "default"
    if color_scale == "risk-semantic" and not _RISK_HEX_RE.search(svg):
        blockers.append(
            "risk-palette: color_scale='risk-semantic' is set but none of the "
            "approved risk hex codes (#C00000 CRITICAL / #E36C09 HIGH / "
            "#F2C500 MEDIUM / #4F7942 LOW) were found in the SVG"
        )

    # (e) Deterministic floor checks for html-embed output (vendored scorer)
    output_format = getattr(opts, "output_format", "svg") if opts else "svg"
    if output_format == "html-embed":
        figures = _ven.extract_figures(svg)
        if figures:
            duplicate_indices = _ven.detect_duplicate_geometry(figures)
            for idx, fig in enumerate(figures):
                is_duplicate = idx in duplicate_indices
                fig_scores = _ven.score_figure_deterministic(fig, is_duplicate=is_duplicate)
                for dim in FIGURE_DIMENSIONS:
                    scores[dim] = min(scores[dim], fig_scores.get(dim, QUALITY_FLOOR))

    # Determine pass/fail
    floor_fail = [d for d, v in scores.items() if v < QUALITY_FLOOR]
    for dim in floor_fail:
        if not any(dim in b for b in blockers):
            blockers.append(
                f"dim '{dim}' scored {scores[dim]:.1f} < floor {QUALITY_FLOOR}"
            )

    return LintResult(passed=not blockers, dim_scores=scores, blockers=blockers)


__all__ = ["LintResult", "lint_product", "lint_paper", "lint_figure"]
