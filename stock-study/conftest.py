"""Top-level pytest config. Adds repo root to sys.path."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure compliance/ paths resolve relative to repo root when tests cwd differ.
os.environ.setdefault("COMPLIANCE_RESTRICTED_PATH", str(ROOT / "compliance" / "restricted_issuers.yaml"))
os.environ.setdefault("COMPLIANCE_BANNED_PATH", str(ROOT / "compliance" / "banned_phrases.yaml"))
os.environ.setdefault("COMPLIANCE_DISCLAIMER_PATH", str(ROOT / "compliance" / "disclaimer.txt"))
