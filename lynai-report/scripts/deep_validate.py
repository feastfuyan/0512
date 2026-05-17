#!/usr/bin/env python3
"""
deep_validate.py — Paper.Validator integration for Critic-A R3 (v1.4, D-14)
============================================================================

Used by Critic-A BEFORE finalizing R3 (Data Defensibility) score: invokes the
paper skill's Deep Research validator to cross-check key numerical claims in
the draft against public academic / market data sources (CrossRef, OpenAlex,
Semantic Scholar, etc. as configured in the paper skill).

Wraps:
    ~/.claude/skills/paper/agents/validator.py (ValidatorAgent)

Usage:
    python deep_validate.py \\
        --input artifacts/draft_v0.md
        --analysis-brief artifacts/analysis_brief.md
        --out artifacts/deep_validation_report.json
        [--max-claims 15]

Output schema:
    {
      "draft_revision":  0,
      "claims_checked":  15,
      "validated":       [{"claim": "Top 5 hold 45% of cap", "verdict": "supported", "evidence": "...", "confidence": 0.92}],
      "unsupported":     [...],
      "needs_more_data": [...],
      "r3_score_hint":   9.6,
      "verdict":         "OK" | "WARNINGS" | "VALIDATOR_UNAVAILABLE"
    }

Failure mode: if paper.validator unavailable OR external API is rate-limited,
emit verdict "VALIDATOR_UNAVAILABLE" with r3_score_hint=null (Critic-A falls
back to citation-only review).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


PAPER_VALIDATOR = Path.home() / ".claude" / "skills" / "paper" / "agents" / "validator.py"


def _load_validator_module():
    if not PAPER_VALIDATOR.exists():
        return None
    spec = importlib.util.spec_from_file_location("paper_validator", PAPER_VALIDATOR)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:
        print(f"[deep_validate] failed to load paper.validator: {exc}", file=sys.stderr)
        return None


# --- Lightweight claim extraction (markdown) ---
# Picks high-signal sentences: those with a number + a verb/noun signaling a claim.
CLAIM_RE = re.compile(
    r"(?:[A-Z][^.!?]*?\b\d+(?:\.\d+)?\s*(?:%|percent|%|tonnes?|kt|Mt|million|billion|bn|US\$|/oz|/t)\b[^.!?]*[.!?])"
)


def _extract_claims(text: str, max_claims: int = 15) -> list[str]:
    seen = set()
    claims = []
    for m in CLAIM_RE.finditer(text):
        sentence = re.sub(r"\s+", " ", m.group(0)).strip()
        if sentence in seen:
            continue
        seen.add(sentence)
        claims.append(sentence)
        if len(claims) >= max_claims:
            break
    return claims


def _call_paper_validator(claims: list[str]) -> list[dict] | None:
    """Invoke paper.ValidatorAgent.validate_claims() if available."""
    mod = _load_validator_module()
    if mod is None or not hasattr(mod, "ValidatorAgent"):
        return None
    try:
        agent = mod.ValidatorAgent()
        if hasattr(agent, "validate_claims"):
            return agent.validate_claims(claims)
        if hasattr(agent, "validate"):
            return [agent.validate(c) for c in claims]
        if hasattr(agent, "deep_research"):
            return [agent.deep_research(c) for c in claims]
    except Exception as exc:
        print(f"[deep_validate] ValidatorAgent invocation failed: {exc}", file=sys.stderr)
    return None


def _normalize_result(r) -> dict:
    """Coerce ValidatorAgent's various result shapes into our schema."""
    if isinstance(r, dict):
        return {
            "claim":      r.get("claim", ""),
            "verdict":    r.get("verdict") or r.get("status") or "unknown",
            "evidence":   r.get("evidence") or r.get("source") or "",
            "confidence": float(r.get("confidence", r.get("score", 0.0)) or 0.0),
        }
    return {"claim": str(r), "verdict": "unknown", "evidence": "", "confidence": 0.0}


def _r3_score_hint(supported: int, unsupported: int, total: int) -> float | None:
    """Map deep-validation findings to a heuristic R3 score (rubric anchors per
    docs/02_RUBRIC_REFERENCE.md). Critic-A may override with judgment."""
    if total == 0:
        return None
    pct_supported = supported / total
    if pct_supported >= 0.95 and unsupported == 0:
        return 9.8
    if pct_supported >= 0.90:
        return 9.6
    if pct_supported >= 0.80:
        return 9.4
    if pct_supported >= 0.60:
        return 9.0
    return 8.0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LynAI deep_validate (v1.4, D-14: paper.validator integration)")
    p.add_argument("--input", required=True, help="draft_v{n}.md")
    p.add_argument("--analysis-brief", default=None, help="Optional analysis_brief.md to pull additional claims")
    p.add_argument("--out", required=True)
    p.add_argument("--draft-revision", type=int, default=0)
    p.add_argument("--max-claims", type=int, default=15)
    args = p.parse_args(argv)

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"FATAL: input not found: {input_path}", file=sys.stderr)
        return 2

    text = input_path.read_text(encoding="utf-8")
    if args.analysis_brief:
        ab = Path(args.analysis_brief)
        if ab.exists():
            text = text + "\n\n" + ab.read_text(encoding="utf-8")

    claims = _extract_claims(text, max_claims=args.max_claims)

    raw_results = _call_paper_validator(claims)
    backend = "paper_validator"
    if raw_results is None:
        backend = "unavailable"
        report = {
            "version": "1.4",
            "scan_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "draft_revision": args.draft_revision,
            "claims_checked": 0,
            "candidate_claims": claims,
            "validated": [],
            "unsupported": [],
            "needs_more_data": [],
            "r3_score_hint": None,
            "backend": backend,
            "paper_skill_installed": PAPER_VALIDATOR.exists(),
            "verdict": "VALIDATOR_UNAVAILABLE",
            "note": "paper.validator not installed or returned no usable result; Critic-A falls back to citation-only R3 review.",
        }
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[warn] deep_validate verdict={report['verdict']}  claims={len(claims)}")
        return 0

    normalized = [_normalize_result(r) for r in raw_results]
    supported   = [r for r in normalized if r["verdict"] in ("supported", "ok", "verified")]
    unsupported = [r for r in normalized if r["verdict"] in ("unsupported", "fail", "contradicted")]
    needs_more  = [r for r in normalized if r not in supported and r not in unsupported]

    r3_hint = _r3_score_hint(len(supported), len(unsupported), len(normalized))

    report = {
        "version": "1.4",
        "scan_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "draft_revision": args.draft_revision,
        "claims_checked": len(normalized),
        "validated":       supported,
        "unsupported":     unsupported,
        "needs_more_data": needs_more,
        "r3_score_hint":   r3_hint,
        "backend":         backend,
        "paper_skill_installed": True,
        "verdict": "OK" if not unsupported else "WARNINGS",
    }
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] deep_validate verdict={report['verdict']}  supported={len(supported)}/{len(normalized)}  R3_hint={r3_hint}")
    return 0 if report["verdict"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
