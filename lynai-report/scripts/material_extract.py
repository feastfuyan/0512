#!/usr/bin/env python3
"""
material_extract.py — Paper.Collector integration for Analyst upstream (v1.4, D-14)
====================================================================================

Used by the Analyst BEFORE composing thesis: scans ${LYNAI_UPLOADS_DIR} for any
user-supplied raw materials (DOCX, PDF, Excel, CSV, JSON, image), classifies
them, extracts core information, and produces a `material_inventory.json`
that gets folded into the Analyst's context.

This eliminates the v1.0–v1.3 friction where the user had to describe what they
uploaded; the Analyst now sees a structured inventory automatically.

Wraps:
    ~/.claude/skills/paper/agents/collector.py (CollectorAgent)

Usage:
    python material_extract.py \\
        --uploads-dir /mnt/user-data/uploads      # or override via env
        --out artifacts/material_inventory.json

Output schema:
    {
      "scan_timestamp": "2026-05-14T10:00:00Z",
      "uploads_dir":    "/mnt/user-data/uploads",
      "files":          [
        {"path": "...", "type": "geological_report" | "csv_data" | "image" | "pdf_paper" | "other",
         "size_bytes": int, "key_findings": ["..."], "extracted_text_preview": "..."}
      ],
      "summary":        {"by_type": {"pdf_paper": 3, "csv_data": 2, ...}, "total_size_mb": 14.2},
      "verdict":        "OK" | "EMPTY" | "PAPER_SKILL_UNAVAILABLE"
    }

Failure mode: if paper.collector unavailable, falls back to a lightweight
file listing (path + type-by-extension + size) so Analyst still has SOMETHING.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


PAPER_COLLECTOR = Path.home() / ".claude" / "skills" / "paper" / "agents" / "collector.py"

EXT_TYPE_MAP = {
    ".pdf":   "pdf_paper",
    ".docx":  "docx_report",
    ".doc":   "docx_report",
    ".xlsx":  "excel_data",
    ".xls":   "excel_data",
    ".csv":   "csv_data",
    ".tsv":   "csv_data",
    ".json":  "json_data",
    ".png":   "image",
    ".jpg":   "image",
    ".jpeg":  "image",
    ".gif":   "image",
    ".webp":  "image",
    ".md":    "markdown_note",
    ".txt":   "text_note",
}


def _load_collector():
    if not PAPER_COLLECTOR.exists():
        return None
    spec = importlib.util.spec_from_file_location("paper_collector", PAPER_COLLECTOR)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:
        print(f"[material_extract] failed to load paper.collector: {exc}", file=sys.stderr)
        return None


def _heuristic_classify(p: Path) -> dict:
    """In-house lightweight inventory entry when paper.collector unavailable."""
    suffix = p.suffix.lower()
    type_ = EXT_TYPE_MAP.get(suffix, "other")
    size = p.stat().st_size if p.exists() else 0

    preview = ""
    if type_ in ("markdown_note", "text_note", "csv_data", "json_data") and size < 200_000:
        try:
            preview = p.read_text(encoding="utf-8", errors="replace")[:500]
        except Exception:
            preview = ""
    return {
        "path": str(p),
        "type": type_,
        "size_bytes": size,
        "key_findings": [],
        "extracted_text_preview": preview,
    }


def _call_paper_collector(uploads_dir: Path) -> list[dict] | None:
    """Try the paper.CollectorAgent for richer extraction."""
    mod = _load_collector()
    if mod is None:
        return None
    if not hasattr(mod, "CollectorAgent"):
        return None
    try:
        agent = mod.CollectorAgent(material_dir=str(uploads_dir)) if "material_dir" in mod.CollectorAgent.__init__.__code__.co_varnames else mod.CollectorAgent()
        # Each CollectorAgent flavor exposes slightly different methods; try the
        # most common signatures in order:
        if hasattr(agent, "scan_and_extract"):
            result = agent.scan_and_extract()
            if isinstance(result, list):
                return result
            if hasattr(result, "to_dict"):
                return result.to_dict().get("files", [])
        if hasattr(agent, "scan_directory"):
            inv = agent.scan_directory(str(uploads_dir))
            files = []
            for f in getattr(inv, "files", []) or []:
                files.append({
                    "path": getattr(f, "path", str(f)),
                    "type": getattr(f, "category", "other"),
                    "size_bytes": getattr(f, "size_bytes", 0),
                    "key_findings": getattr(f, "key_findings", []),
                    "extracted_text_preview": (getattr(f, "extracted_text", "") or "")[:500],
                })
            return files
    except Exception as exc:
        print(f"[material_extract] CollectorAgent path failed: {exc}", file=sys.stderr)
    return None


def _summarize(files: list[dict]) -> dict:
    by_type: dict[str, int] = {}
    total_size = 0
    for f in files:
        by_type[f["type"]] = by_type.get(f["type"], 0) + 1
        total_size += int(f.get("size_bytes", 0))
    return {
        "by_type": by_type,
        "total_files": len(files),
        "total_size_mb": round(total_size / (1024 * 1024), 2),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LynAI material_extract (v1.4, D-14: paper.collector integration)")
    p.add_argument("--uploads-dir", default=os.environ.get("LYNAI_UPLOADS_DIR", "/mnt/user-data/uploads"))
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)

    uploads = Path(args.uploads_dir)
    backend = "in_house_heuristic"
    files: list[dict] = []

    if uploads.exists() and uploads.is_dir():
        # Path A: paper.collector
        result = _call_paper_collector(uploads)
        if result is not None:
            files = result
            backend = "paper_collector"
        else:
            # Path B: heuristic file walk
            for p in sorted(uploads.rglob("*")):
                if p.is_file() and not p.name.startswith("."):
                    files.append(_heuristic_classify(p))

    verdict = "OK"
    if not files:
        if not uploads.exists():
            verdict = "UPLOADS_DIR_MISSING"
        else:
            verdict = "EMPTY"
    if backend == "in_house_heuristic" and not PAPER_COLLECTOR.exists():
        # Add an informational marker but don't override OK/EMPTY verdict
        pass

    report = {
        "version": "1.4",
        "scan_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "uploads_dir": str(uploads),
        "backend": backend,
        "paper_skill_installed": PAPER_COLLECTOR.exists(),
        "files": files,
        "summary": _summarize(files),
        "verdict": verdict,
    }
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] material_extract verdict={verdict}  files={len(files)}  backend={backend}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
