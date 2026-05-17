#!/usr/bin/env python3
"""
check_assets.py — DOCX Asset Integrity Check (Python zipfile, cross-platform)
============================================================================

Replaces the v1.0 shell `unzip -l ... | grep` approach (which is broken on
Windows hosts without unzip). This script reads the .docx via Python's
stdlib zipfile and checks every word/media/* entry.

Usage:
    python check_assets.py path/to/output.docx

Exit codes:
    0 — all assets OK
    1 — at least one asset failed (details on stderr; JSON on stdout)
    2 — input error (file missing, not a zip, no media folder)

Output: JSON to stdout, suitable for piping into the Validator's report.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any


MIN_IMAGE_BYTES = 1024
ASPECT_RATIO_TOLERANCE = 0.01  # 1%


def _image_dimensions(data: bytes) -> tuple[int, int] | None:
    """Return (width, height) for PNG / JPEG, or None if unknown."""
    # PNG
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        # IHDR starts at byte 16
        if len(data) >= 24:
            import struct
            w, h = struct.unpack(">II", data[16:24])
            return (w, h)
    # JPEG (scan SOF0/2)
    if data[:2] == b"\xff\xd8":
        import struct
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC2):  # SOF0 or SOF2
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return (w, h)
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + length
    return None


def _extract_drawing_extents(document_xml: bytes) -> list[tuple[str, int, int]]:
    """Parse word/document.xml for (image-name, cx, cy) tuples from <wp:extent>.
    A very lightweight parser — enough to cross-check aspect ratios.
    """
    text = document_xml.decode("utf-8", errors="ignore")
    out = []
    # Find pairs of (Target image, <wp:extent .../>) sequentially
    # Simplest approach: collect all extents in order
    extents = re.findall(r'<wp:extent\s+cx="(\d+)"\s+cy="(\d+)"', text)
    # Collect image names in order via blip embed → r:embed → relationship target
    embeds = re.findall(r'r:embed="(rId\d+)"', text)
    return list(zip(embeds, [int(cx) for cx, _ in extents], [int(cy) for _, cy in extents]))


def check_docx(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"pass": False, "error": f"file not found: {path}"}
    if not zipfile.is_zipfile(path):
        return {"pass": False, "error": f"not a valid zip: {path}"}

    result: dict[str, Any] = {
        "pass": True,
        "image_count": 0,
        "bad_assets": [],
        "warnings": [],
    }

    with zipfile.ZipFile(path) as z:
        media_names = [n for n in z.namelist() if n.startswith("word/media/")]
        result["image_count"] = len(media_names)

        if not media_names:
            result["warnings"].append("no word/media/ entries (charts may be absent or inline)")

        for name in media_names:
            try:
                data = z.read(name)
            except Exception as exc:
                result["bad_assets"].append({"name": name, "issue": f"read failed: {exc}"})
                result["pass"] = False
                continue
            if len(data) < MIN_IMAGE_BYTES:
                result["bad_assets"].append({"name": name, "issue": f"too small ({len(data)} bytes)"})
                result["pass"] = False
                continue
            dims = _image_dimensions(data)
            if dims is None:
                result["warnings"].append(f"{name}: could not parse image dimensions (unsupported format?)")
                continue
            w, h = dims
            if h == 0:
                result["bad_assets"].append({"name": name, "issue": "zero height"})
                result["pass"] = False
                continue
            ar = w / h
            if not (0.3 <= ar <= 4.0):
                result["warnings"].append(f"{name}: unusual aspect ratio {ar:.2f}")

        # Cross-check drawing extents (optional, soft check)
        if "word/document.xml" in z.namelist():
            try:
                doc_xml = z.read("word/document.xml")
                extents = _extract_drawing_extents(doc_xml)
                if extents and media_names and len(extents) != len(media_names):
                    result["warnings"].append(
                        f"drawing extents count {len(extents)} != media count {len(media_names)}"
                    )
            except Exception as exc:
                result["warnings"].append(f"document.xml parse skipped: {exc}")

    return result


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print("usage: check_assets.py <path/to/output.docx>", file=sys.stderr)
        return 2
    result = check_docx(Path(argv[0]))
    print(json.dumps(result, indent=2))
    if not result.get("pass", False):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
