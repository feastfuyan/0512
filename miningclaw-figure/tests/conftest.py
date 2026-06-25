"""conftest.py — adds the skill root to sys.path so tests can import figure_spec, parity, etc."""
import sys, pathlib, os

SK = pathlib.Path(__file__).parent.parent
if str(SK) not in sys.path:
    sys.path.insert(0, str(SK))

# Product module (optional — only needed for parity tests).
# Set MININGCLAWD_SRC env var to lynai-miningclawd-monorepo/services/report/src.
_PROD_RAW = os.environ.get("MININGCLAWD_SRC", "")
PROD = pathlib.Path(_PROD_RAW) if _PROD_RAW else pathlib.Path("NOT_CONFIGURED")
if PROD.exists() and str(PROD) not in sys.path:
    sys.path.insert(0, str(PROD))
