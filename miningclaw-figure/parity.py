# parity.py
# Pins the product's figure-quality module constants and public function names
# so that any drift in report_service.runtime.quality.{figure_checks,chart_registry,rubric}
# is immediately caught by the tripwire test.
import ast, json, sys, pathlib, os

# Set MININGCLAWD_SRC env var to lynai-miningclawd-monorepo/services/report/src
# for parity tests; default is intentionally non-existent to require explicit config.
_PROD_SRC_RAW = os.environ.get("MININGCLAWD_SRC", "")
PROD_SRC = pathlib.Path(_PROD_SRC_RAW) if _PROD_SRC_RAW else pathlib.Path("NOT_CONFIGURED")
_FILES = ["runtime/quality/figure_checks.py", "runtime/quality/chart_registry.py", "runtime/quality/rubric.py"]


def product_quality_path() -> pathlib.Path:
    return PROD_SRC / "report_service"


def _normalize(v: object) -> object:
    """Normalize to JSON-compatible types: tuples → lists, sets → sorted lists.

    Note: set/frozenset literal contents (via _extract_const_value) ARE pinned.
    Only truly non-literal expressions fall back to '<expr>' marker.
    """
    if isinstance(v, (tuple, set, frozenset)):
        return [_normalize(x) for x in sorted(v) if isinstance(x, str)] if isinstance(v, (set, frozenset)) else [_normalize(x) for x in v]
    if isinstance(v, dict):
        return {k: _normalize(vv) for k, vv in v.items()}
    return v


def _sig_of(path: pathlib.Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    consts, funcs = {}, []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    consts[t.id] = _extract_const_value(node.value)
        elif isinstance(node, ast.AnnAssign):
            # Annotated assignment: CONST: type = value
            if isinstance(node.target, ast.Name) and node.target.id.isupper() and node.value is not None:
                consts[node.target.id] = _extract_const_value(node.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            funcs.append(node.name)
    return {"constants": consts, "public_funcs": sorted(funcs)}


def _extract_const_value(node: ast.expr) -> object:
    """Extract constant value, handling set/frozenset literals specially."""
    # Check if this is a frozenset(...) or set(...) call with a single literal argument
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in ("frozenset", "set"):
            if len(node.args) == 1 and not node.keywords:
                arg = node.args[0]
                # If the argument is a set, list, or tuple literal, extract its elements
                if isinstance(arg, (ast.Set, ast.List, ast.Tuple)):
                    try:
                        elements = ast.literal_eval(arg)
                        return sorted([x for x in elements if isinstance(x, str)])
                    except Exception:
                        return "<expr>"
    # Fall back to ast.literal_eval for other cases
    try:
        return _normalize(ast.literal_eval(node))
    except Exception:
        return "<expr>"


def constant_signature() -> dict:
    base = product_quality_path()
    # _FILES are relative to report_service/ (e.g. "runtime/quality/figure_checks.py")
    return {f: _sig_of(base / f) for f in _FILES}


def verify_manifest() -> tuple[bool, list[str]]:
    pinned = json.loads((pathlib.Path(__file__).with_name("parity_manifest.json")).read_text("utf-8"))
    live = constant_signature()
    drift = [f for f in _FILES if pinned.get(f) != live.get(f)]
    return (not drift, drift)


def load_product_module(name: str):
    p = str(product_quality_path().parent)
    if p not in sys.path:
        sys.path.insert(0, p)
    import importlib
    return importlib.import_module(f"report_service.runtime.quality.{name}")
