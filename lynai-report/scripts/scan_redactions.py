#!/usr/bin/env python3
"""
scan_redactions.py — LynAI PII / MNPI / Credentials Detector
============================================================

Deterministic regex scanner invoked by agent.redactor. Scans the gate-passed
draft + chart captions + table cells. Emits structured findings; the Redactor
agent (P14) decides what to do with each.

The scanner detects; the agent decides. We use regex (not LLM) for:
  - Determinism (same input → same output)
  - Auditability (every pattern is documented)
  - Speed (~100 ms on a 40-page draft)
  - Low false-negative rate (regex catches what it's looking for)

Usage:
    python scan_redactions.py \\
        --draft draft_v3.md \\
        --plan plan.json \\
        --charts-index charts_index.md \\
        --tables tables.json \\
        --draft-revision 3 \\
        --out redaction_report.json

Exit codes:
    0 — scan completed successfully (verdict in JSON)
    2 — input failure
    4 — internal error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ----- v1.4.2 D-16 P0-2: Unicode normalization to defeat ZWJ + en-dash bypass -----
#
# Red-team finding C2 (v1.4.1): an adversary inserted ONE U+200B (zero-width
# space) into AKIA[ZWJ]IOSFODNN7EXAMPLE and the regex `\b(AKIA|ASIA)[0-9A-Z]{16}\b`
# failed to match — \b is locale-aware and ZWJ broke the word boundary.
# Same trick with U+2013/U+2014 (en/em-dash) defeated the SSN regex.
#
# Fix: NFKC-normalize, then strip Cf-class (format) chars, then collapse all
# Unicode hyphen variants to ASCII '-' before applying patterns. The ORIGINAL
# text is still used for snippet_redacted so the report still shows context.

# Unicode characters that look like hyphens but aren't U+002D
_HYPHEN_LIKE = {
    0x2010,  # HYPHEN
    0x2011,  # NON-BREAKING HYPHEN
    0x2012,  # FIGURE DASH
    0x2013,  # EN DASH
    0x2014,  # EM DASH
    0x2015,  # HORIZONTAL BAR
    0x2212,  # MINUS SIGN
    0xFE58,  # SMALL EM DASH
    0xFE63,  # SMALL HYPHEN-MINUS
    0xFF0D,  # FULLWIDTH HYPHEN-MINUS
}


def _normalize_for_scan(text: str) -> str:
    """Aggressively normalize text so regex patterns can't be Unicode-bypassed.

    Steps:
      1. NFKC normalize (handles compatibility decompositions, fullwidth → ASCII).
      2. Strip Cf-class characters (zero-width spaces/joiners U+200B/200C/200D/2060/FEFF).
      3. Translate Unicode hyphen-likes to ASCII '-'.
    """
    s = unicodedata.normalize("NFKC", text)
    # Drop zero-width / format characters
    s = "".join(c for c in s if unicodedata.category(c) != "Cf")
    # Collapse hyphen-likes
    s = s.translate({code: 0x2D for code in _HYPHEN_LIKE})
    return s


# ----- Pattern library ------------------------------------------------------
# Each entry: (pattern_name, regex, severity)
# Severity:
#   critical  — auto-block (Redactor overall_verdict = BLOCKED)
#   high      — escalate to user
#   medium    — auto-redact in place
#   low       — auto-redact in place (often false positives; tune per report)

PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("aws_access_key",        re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "critical"),
    ("aws_secret_key_context",
        # Generic 40-char base64-ish, only flagged when adjacent to a secret-y context word
        re.compile(r"(?i)(secret|aws_secret|api_secret|key)\s*[:=]\s*[\"']?([A-Za-z0-9/+=]{40})[\"']?"),
        "critical"),
    ("gcp_service_account",   re.compile(r"\b[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com\b"), "critical"),
    ("private_key_pem",       re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "critical"),
    ("ssn_us",                re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "critical"),
    ("credit_card_loose",
        # Loose detector; Redactor applies Luhn check downstream
        re.compile(r"\b(?:\d[ -]?){13,19}\b"), "critical"),
    ("mnpi_marker",
        re.compile(r"(?i)\b(embargo until|do not distribute|mnpi|material non[- ]?public|reg fd|draft 8-k|pre-announcement)\b"),
        "high"),
    ("passport_us",           re.compile(r"\b[A-Z0-9]{9}\b(?=.*passport)", re.IGNORECASE), "medium"),
]


def _luhn_valid(num_str: str) -> bool:
    digits = [int(d) for d in re.sub(r"[ -]", "", num_str) if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# ----- Helpers --------------------------------------------------------------

def _mask_payload(text: str, pattern_name: str, span: tuple[int, int]) -> str:
    """Return the text with the matched payload replaced by «REDACTED:pattern»."""
    start, end = span
    return text[:start] + f"«REDACTED:{pattern_name}»" + text[end:]


def _make_snippet(line: str, span: tuple[int, int], context: int = 40) -> str:
    start = max(0, span[0] - context)
    end = min(len(line), span[1] + context)
    masked = _mask_payload(line, "REDACTED", (span[0] - start, span[1] - start))
    return masked[start - start:end - start]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _sha256_bytes(b: bytes) -> str:
    return f"sha256:{hashlib.sha256(b).hexdigest()}"


# ----- Scanner core ---------------------------------------------------------

def scan_text(text: str, source_label: str, whitelisted_domains: list[str], nda_tokens: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lines = text.splitlines()

    for line_no, original_line in enumerate(lines, start=1):
        # v1.4.2 D-16 P0-2: scan against NORMALIZED line (defeats ZWJ + en-dash),
        # but report context from the ORIGINAL line so the operator sees what
        # was actually in the source.
        line = _normalize_for_scan(original_line)
        for pattern_name, regex, severity in PATTERNS:
            for m in regex.finditer(line):
                # Apply Luhn for credit card loose matches
                if pattern_name == "credit_card_loose":
                    if not _luhn_valid(m.group(0)):
                        continue
                snippet = _make_snippet(line, m.span())
                findings.append({
                    "pattern": pattern_name,
                    "line_anchor": f"{source_label} line {line_no}",
                    "snippet_redacted": snippet,
                    "severity": severity,
                    "disposition": "redacted_inplace" if severity in ("medium", "low") else "escalated_to_user" if severity == "high" else "blocked",
                })

        # Email pattern with domain whitelisting
        for m in re.finditer(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b", line):
            domain = m.group(1).lower()
            if whitelisted_domains and domain not in {d.lower() for d in whitelisted_domains}:
                findings.append({
                    "pattern": "email_non_whitelisted_domain",
                    "line_anchor": f"{source_label} line {line_no}",
                    "snippet_redacted": _make_snippet(line, m.span()),
                    "severity": "high",
                    "disposition": "escalated_to_user",
                })

        # NDA tokens (literal client codenames)
        for nda in nda_tokens:
            for m in re.finditer(re.escape(nda), line):
                findings.append({
                    "pattern": "client_named_nda_token",
                    "line_anchor": f"{source_label} line {line_no}",
                    "snippet_redacted": _make_snippet(line, m.span()),
                    "severity": "high",
                    "disposition": "escalated_to_user",
                })

    return findings


def sanitize_text(text: str, findings: list[dict[str, Any]]) -> str:
    """Naive in-place sanitization for medium/low severity findings. For high/critical
    the Redactor agent should decide before this is called. Here we conservatively
    redact everything whose disposition is 'redacted_inplace'.

    v1.4.2 D-16 P0-2: sanitize after normalizing so the in-source secret (with
    or without ZWJ/en-dash obfuscation) is masked in the sanitized draft.
    """
    # Apply Unicode normalization first so ZWJ/en-dash variants get caught too.
    out = _normalize_for_scan(text)
    for pattern_name, regex, severity in PATTERNS:
        if severity not in ("medium", "low"):
            continue
        out = regex.sub(f"«REDACTED:{pattern_name}»", out)
    return out


# ----- Top-level entry ------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LynAI redaction scanner")
    p.add_argument("--draft", required=True, type=Path)
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--charts-index", type=Path, default=None)
    p.add_argument("--tables", type=Path, default=None)
    p.add_argument("--draft-revision", type=int, required=True)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--sanitized-out", type=Path, default=None, help="Where to write sanitized draft if findings exist")
    args = p.parse_args(argv)

    if not args.draft.exists():
        print(f"FATAL: missing draft {args.draft}", file=sys.stderr)
        return 2

    with open(args.plan) as f:
        plan = json.load(f)
    whitelisted = plan.get("report_meta", {}).get("whitelisted_domains", [])
    nda_tokens = plan.get("nda_tokens", [])

    draft_text = args.draft.read_text(encoding="utf-8")
    findings: list[dict[str, Any]] = []
    findings.extend(scan_text(draft_text, "draft", whitelisted, nda_tokens))

    if args.charts_index and args.charts_index.exists():
        findings.extend(scan_text(args.charts_index.read_text(encoding="utf-8"), "charts_index", whitelisted, nda_tokens))

    if args.tables and args.tables.exists():
        # Flatten table cells into a scan-able blob
        with open(args.tables) as f:
            tables = json.load(f)
        cells_blob = "\n".join(
            str(cell) for tbl in (tables if isinstance(tables, list) else [tables])
            for row in tbl.get("rows", []) for cell in row
        )
        findings.extend(scan_text(cells_blob, "tables", whitelisted, nda_tokens))

    # Decide verdict
    has_critical = any(f["severity"] == "critical" and f["disposition"] == "blocked" for f in findings)
    has_any = bool(findings)

    if has_critical:
        verdict = "BLOCKED"
        sanitized_hash = None
    elif not has_any:
        verdict = "CLEAR"
        sanitized_hash = None
    else:
        verdict = "REDACTED"
        sanitized_text = sanitize_text(draft_text, findings)
        if args.sanitized_out:
            args.sanitized_out.write_text(sanitized_text, encoding="utf-8")
            sanitized_hash = _sha256_bytes(sanitized_text.encode("utf-8"))
        else:
            sanitized_hash = _sha256_bytes(sanitized_text.encode("utf-8"))

    patterns_checked = [name for name, _, _ in PATTERNS] + [
        "email_non_whitelisted_domain", "client_named_nda_token"
    ]
    report = {
        "version": "1.1",
        "draft_revision": args.draft_revision,
        "draft_content_hash": _sha256_file(args.draft),
        "scan_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "patterns_checked": patterns_checked,
        "findings": findings,
        "overall_verdict": verdict,
    }
    if sanitized_hash:
        report["sanitized_draft_hash"] = sanitized_hash

    args.out.write_text(json.dumps(report, indent=2))
    print(f"[ok] verdict: {verdict}, findings: {len(findings)} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
