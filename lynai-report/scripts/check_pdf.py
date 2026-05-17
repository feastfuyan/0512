#!/usr/bin/env python3
"""
check_pdf.py — LynAI PDF deliverable integrity check (v1.2)

Validates the .pdf that LibreOffice rendered from the .docx, treating it as
a first-class deliverable (per docs/00_DECISIONS.md §D-11) rather than a
disposable validator side-effect.

Checks:
  1. File exists and size > 5 KB
  2. PDF header magic bytes ("%PDF-")
  3. PDF trailer present ("%%EOF" within last 1024 bytes)
  4. Page count parsed and ≥ expected minimum (default 2)
  5. Optional: page-count parity with companion .docx producer_log

Usage:
    python check_pdf.py <path/to/file.pdf> [--min-pages N] [--producer-log path/to/producer_log.json]

Exit codes:
    0 — all checks passed
    1 — one or more checks failed (details on stdout as JSON)
    2 — input error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


MIN_PDF_BYTES = 5 * 1024


def _parse_pdf_metadata(data: bytes) -> dict:
    """Lightweight PDF parsing without external libs.

    Looks for /Type /Page references (excluding /Pages) to count pages,
    and verifies header + trailer.
    """
    out: dict = {
        "header_ok": False,
        "trailer_ok": False,
        "pages": 0,
        "version": None,
    }

    # Header — must be %PDF-X.Y in first 8 bytes
    if data[:5] == b"%PDF-":
        out["header_ok"] = True
        ver_match = re.match(rb"%PDF-(\d+\.\d+)", data[:10])
        if ver_match:
            out["version"] = ver_match.group(1).decode("ascii", errors="replace")

    # Trailer — %%EOF in last 1024 bytes
    tail = data[-1024:] if len(data) > 1024 else data
    if b"%%EOF" in tail:
        out["trailer_ok"] = True

    # Page count — count /Type /Page (but NOT /Type /Pages)
    # Use a regex that requires the next char after "Page" to NOT be "s"
    pages = re.findall(rb"/Type\s*/Page(?!s)", data)
    out["pages"] = len(pages)

    return out


def check_pdf(path: Path, min_pages: int = 2, expected_pages: int | None = None) -> dict:
    result: dict = {
        "pass": True,
        "file": str(path),
        "size_bytes": 0,
        "checks": {},
        "warnings": [],
    }

    if not path.exists():
        result["pass"] = False
        result["checks"]["exists"] = False
        result["error"] = "file not found"
        return result
    result["checks"]["exists"] = True

    data = path.read_bytes()
    result["size_bytes"] = len(data)
    if len(data) < MIN_PDF_BYTES:
        result["pass"] = False
        result["checks"]["size_min"] = False
        result["error"] = f"file too small ({len(data)} bytes < {MIN_PDF_BYTES})"
        return result
    result["checks"]["size_min"] = True

    meta = _parse_pdf_metadata(data)
    result["checks"]["header_ok"] = meta["header_ok"]
    result["checks"]["trailer_ok"] = meta["trailer_ok"]
    result["pages"] = meta["pages"]
    result["pdf_version"] = meta["version"]

    if not meta["header_ok"]:
        result["pass"] = False
        result["error"] = "missing %PDF- header"
        return result
    if not meta["trailer_ok"]:
        result["pass"] = False
        result["error"] = "missing %%EOF trailer (likely truncated)"
        return result

    if meta["pages"] < min_pages:
        result["pass"] = False
        result["checks"]["pages_min"] = False
        result["error"] = f"page count {meta['pages']} < required {min_pages}"
        return result
    result["checks"]["pages_min"] = True

    if expected_pages is not None and abs(meta["pages"] - expected_pages) > 1:
        result["warnings"].append(
            f"PDF page count {meta['pages']} differs from expected {expected_pages} by > 1"
        )

    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LynAI PDF deliverable integrity check (v1.2)")
    p.add_argument("pdf", type=Path, help="Path to <slug>.pdf")
    p.add_argument("--min-pages", type=int, default=2)
    p.add_argument("--producer-log", type=Path, default=None,
                   help="Path to producer_log.json (used to read expected page count if available)")
    args = p.parse_args(argv)

    expected_pages: int | None = None
    if args.producer_log and args.producer_log.exists():
        try:
            log = json.loads(args.producer_log.read_text(encoding="utf-8"))
            expected_pages = log.get("pages") or log.get("expected_pages")
        except Exception:
            pass  # producer_log optional; ignore parse errors

    result = check_pdf(args.pdf, min_pages=args.min_pages, expected_pages=expected_pages)
    print(json.dumps(result, indent=2))
    return 0 if result.get("pass", False) else 1


if __name__ == "__main__":
    sys.exit(main())
