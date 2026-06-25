import sys, pathlib, os
import pytest

# ---------------------------------------------------------------------------
# MININGCLAWD_SRC env var — set to path of lynai-miningclawd-monorepo
# services/report/src to run these parity tests.  Skip gracefully otherwise.
# ---------------------------------------------------------------------------
_PROD_RAW = os.environ.get("MININGCLAWD_SRC", "")
PROD = pathlib.Path(_PROD_RAW) if _PROD_RAW else pathlib.Path("NOT_CONFIGURED")

pytestmark = pytest.mark.skipif(
    not PROD.exists(),
    reason="Set MININGCLAWD_SRC env var to lynai-miningclawd-monorepo/services/report/src",
)

if PROD.exists() and str(PROD) not in sys.path:
    sys.path.insert(0, str(PROD))

try:
    from report_service.runtime.quality import figure_checks as prod_fc
    from report_service.runtime.quality import chart_registry as prod_reg
    _PROD_AVAILABLE = True
except ImportError:
    prod_fc = None
    prod_reg = None
    _PROD_AVAILABLE = False


# C1: gate dispatches on wrapper-class -> chart_kind, and the diverging kind literal is exactly this
def test_c1_kind_literals_from_registry():
    kinds = set(prod_reg.CHART_KIND_BY_CLASS.values())
    assert "horizontal-bar" in kinds
    assert "diverging-html-bar" in kinds       # the real literal
    assert "diverging" not in kinds            # the WRONG literal must NOT be a kind

# C2: a real mc-08-style chart in <div class="card"> is gate-blind (0 figures extracted)
def test_c2_mc08_card_is_gate_blind():
    mc08_like = '<div class="card"><svg viewBox="0 0 520 120"><rect x="0" width="40"/></svg></div>'
    assert len(prod_fc.extract_figures(mc08_like)) == 0

# parity manifest must match the live product files (tripwire)
def test_parity_manifest_matches_product():
    from parity import verify_manifest
    ok, drift = verify_manifest()
    assert ok, f"product quality files drifted from pinned manifest: {drift}"


# C3: CHART_WRAPPER_CLASSES content is pinned as a sorted list (NOT "<expr>")
def test_wrapper_classes_content_pinned():
    import json
    from parity import verify_manifest

    manifest_path = pathlib.Path(__file__).parent.parent / "parity_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    chart_reg_entry = manifest.get("runtime/quality/chart_registry.py", {})
    wrapper_classes = chart_reg_entry.get("constants", {}).get("CHART_WRAPPER_CLASSES")

    assert isinstance(wrapper_classes, list), (
        f"CHART_WRAPPER_CLASSES must be a list of strings, not '{wrapper_classes}'. "
        "The parity tripwire is blind to frozenset content drift."
    )

    expected = sorted(["chart-block", "mc-bar-chart", "bar-track", "two-chart", "chart-img"])
    assert wrapper_classes == expected, (
        f"CHART_WRAPPER_CLASSES content mismatch. "
        f"Expected {expected}, got {wrapper_classes}"
    )

    ok, drift = verify_manifest()
    assert ok, f"manifest verification failed after regeneration: {drift}"
