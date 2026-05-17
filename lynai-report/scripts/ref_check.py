#!/usr/bin/env python3
"""
ref_check.py — Paper-skill ref_audit + crossref_lookup integration (v1.4, D-14)
================================================================================

Wrapped invocation of the paper skill's reference-audit toolchain. Used by
Critic-C (R10 Source Discipline) to automatically check:

  * Every in-text citation has a matching entry in the References section
  * Every References entry is actually cited in the body
  * Missing references can be auto-completed via CrossRef API

This makes R10 deduction quantitative rather than judgement-based.

Wraps:
  ~/.claude/skills/paper/scripts/ref_audit.py
  ~/.claude/skills/paper/scripts/crossref_lookup.py

Usage:
    python ref_check.py \\
        --input draft_v0.md                    # or draft.docx
        --out ref_audit_report.json
        [--autocomplete]                       # call CrossRef for missing refs

Output schema:
    {
      "draft_revision":      0,
      "in_text_citations":   ["Author, 2023", ...],
      "references_listed":   ["Author, 2023, Journal ...", ...],
      "missing_in_refs":     ["Author, 2024"],            # cited but no ref entry
      "orphaned_refs":       ["Smith, 2020"],             # listed but never cited
      "autocompleted":       [{"key": "Author, 2024", "entry": "..."}],
      "r10_score_hint":      9.7,                          # heuristic for Critic-C
      "verdict":             "OK" | "ISSUES_FOUND"
    }

Failure mode: if paper skill not installed at ~/.claude/skills/paper/, emit
verdict "PAPER_SKILL_UNAVAILABLE" with empty findings and r10_score_hint=null
(Critic-C falls back to manual review).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path


PAPER_SKILL_ROOT = Path.home() / ".claude" / "skills" / "paper"
PAPER_REF_AUDIT  = PAPER_SKILL_ROOT / "scripts" / "ref_audit.py"
PAPER_CROSSREF   = PAPER_SKILL_ROOT / "scripts" / "crossref_lookup.py"


def _load_module(name: str, path: Path):
    """Dynamic import of paper-skill module by absolute path."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module
    except Exception as exc:
        print(f"[ref_check] failed to load {path.name}: {exc}", file=sys.stderr)
        return None


# --- Lightweight in-house citation extraction (works on markdown OR docx) ---

CITE_RE = re.compile(r"\(([A-Z][A-Za-z\-' ]+(?:et al\.)?,\s+\d{4}[a-z]?)\)|([A-Z][A-Za-z\-']+\s+et\s+al\.,?\s*\d{4}[a-z]?)")


def _extract_citations_from_md(text: str) -> list[str]:
    """Heuristic citation extraction from markdown body (Author, YYYY style)."""
    found = set()
    for m in CITE_RE.finditer(text):
        cite = (m.group(1) or m.group(2) or "").strip()
        if cite:
            found.add(re.sub(r"\s+", " ", cite))
    return sorted(found)


def _extract_references_section(text: str) -> list[str]:
    """Pull lines from a markdown ## References (or ## §10.2 References) section."""
    lines = text.splitlines()
    in_refs = False
    refs = []
    for line in lines:
        if re.match(r"^##+\s+(References|§\d+\.\d+\s+References|§\d+\s*[—\-]\s*References)", line, re.IGNORECASE):
            in_refs = True
            continue
        if in_refs and re.match(r"^##+\s", line):
            break  # next H1/H2 section ends references
        if in_refs and line.strip():
            refs.append(line.strip())
    return refs


def _check_with_paper_skill(input_path: Path):
    """If input is a .docx, prefer paper.ref_audit (its native input is docx)."""
    if input_path.suffix.lower() != ".docx":
        return None
    if not PAPER_REF_AUDIT.exists():
        return None
    ref_audit = _load_module("paper_ref_audit", PAPER_REF_AUDIT)
    if ref_audit is None:
        return None
    try:
        # Most paper.ref_audit scripts expose extract_intext_citations(doc) + extract_reference_list(doc)
        from docx import Document
        doc = Document(str(input_path))
        in_text = list(ref_audit.extract_intext_citations(doc)) if hasattr(ref_audit, "extract_intext_citations") else []
        refs = list(ref_audit.extract_reference_list(doc)) if hasattr(ref_audit, "extract_reference_list") else []
        return {"in_text": in_text, "refs": refs}
    except Exception as exc:
        print(f"[ref_check] paper.ref_audit invocation failed: {exc}", file=sys.stderr)
        return None


def _heuristic_check(input_path: Path) -> dict:
    """Pure in-house path for markdown drafts (no paper-skill dependency)."""
    text = input_path.read_text(encoding="utf-8")
    in_text = _extract_citations_from_md(text)
    refs = _extract_references_section(text)
    return {"in_text": in_text, "refs": refs}


def _normalize_key(s: str) -> str:
    """Author, YYYY → 'author2023' for matching."""
    m = re.search(r"([A-Z][A-Za-z]+).*?(\d{4})", s)
    return (m.group(1).lower() + m.group(2)) if m else s.lower()


def _diff_citations_vs_refs(in_text: list[str], refs: list[str]) -> tuple[list[str], list[str]]:
    ref_keys = {_normalize_key(r) for r in refs}
    in_text_keys = {_normalize_key(c) for c in in_text}
    missing = [c for c in in_text if _normalize_key(c) not in ref_keys]
    orphaned = [r for r in refs if _normalize_key(r) not in in_text_keys]
    return missing, orphaned


def _autocomplete(missing: list[str]) -> list[dict]:
    """Use paper.crossref_lookup to fetch full reference entries."""
    if not PAPER_CROSSREF.exists():
        return []
    crossref = _load_module("paper_crossref", PAPER_CROSSREF)
    if crossref is None or not hasattr(crossref, "lookup_reference"):
        return []
    completed = []
    for cite in missing[:10]:  # cap at 10 lookups per cycle to respect API rate
        try:
            entry = crossref.lookup_reference(cite)
            completed.append({"key": cite, "entry": entry or "(not found)"})
        except Exception as exc:
            completed.append({"key": cite, "entry": f"(lookup failed: {exc})"})
    return completed


def _r10_score_hint(n_missing: int, n_orphan: int, n_total_refs: int) -> float:
    """Map ref-audit findings to a heuristic R10 score (rubric anchors per
    docs/02_RUBRIC_REFERENCE.md). Critic-C may override this with judgment."""
    if n_total_refs == 0:
        return 5.0  # no references section → catastrophic for R10
    issues = n_missing + n_orphan
    if issues == 0:
        return 9.8
    if issues <= 1:
        return 9.6  # 1 polish item — gate passes
    if issues <= 3:
        return 9.4  # gate fails by v1.1 strict-greater-than
    if issues <= 6:
        return 9.0
    return 8.0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LynAI ref_check (v1.4, D-14: paper.ref_audit integration)")
    p.add_argument("--input", required=True, help="draft_v{n}.md or <slug>.docx")
    p.add_argument("--out", required=True, help="output ref_audit_report.json")
    p.add_argument("--draft-revision", type=int, default=0)
    p.add_argument("--autocomplete", action="store_true", help="Call CrossRef API for missing refs")
    args = p.parse_args(argv)

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"FATAL: input not found: {input_path}", file=sys.stderr)
        return 2

    # Path A: docx via paper.ref_audit (preferred for produced reports)
    extracted = _check_with_paper_skill(input_path)
    backend = "paper_ref_audit"

    # Path B: markdown via in-house heuristic (for Drafter intermediate output)
    if extracted is None:
        extracted = _heuristic_check(input_path)
        backend = "in_house_heuristic"

    missing, orphaned = _diff_citations_vs_refs(extracted["in_text"], extracted["refs"])

    autocompleted = []
    if args.autocomplete and missing:
        autocompleted = _autocomplete(missing)

    r10_hint = _r10_score_hint(len(missing), len(orphaned), len(extracted["refs"]))

    report = {
        "version": "1.4",
        "draft_revision": args.draft_revision,
        "input": str(input_path),
        "backend": backend,
        "paper_skill_installed": PAPER_REF_AUDIT.exists(),
        "in_text_citations": extracted["in_text"],
        "references_listed": extracted["refs"][:50],  # cap for log size
        "missing_in_refs": missing,
        "orphaned_refs": orphaned,
        "autocompleted": autocompleted,
        "r10_score_hint": r10_hint,
        "verdict": "OK" if (len(missing) == 0 and len(orphaned) == 0) else "ISSUES_FOUND",
    }
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] ref_check verdict={report['verdict']}  missing={len(missing)}  orphaned={len(orphaned)}  R10_hint={r10_hint}")
    return 0 if report["verdict"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
