#!/usr/bin/env python3
"""
gate_check.py — LynAI Hard Gate Deterministic Core
==================================================

The single source of truth for the gate rule. The Gate-Keeper agent invokes
this script (or imports its functions) to produce a signed gate_token.

The rule (locked, see docs/00_DECISIONS.md §D-1):
    Every dimension's score must be STRICTLY GREATER than 9.5 (i.e. ≥ 9.6).

Usage as CLI:
    GK_TOKEN_SECRET=<hex> python gate_check.py \\
        --scorecard scorecard_v3.json \\
        --draft draft_v3.md \\
        --plan plan.json \\
        --cycle 3 \\
        --out gate_token_v3.json

Usage as library:
    from gate_check import (
        sha256_file, gate_decision, sign_token, build_token, verify_token
    )

Exit codes:
    0  — token written successfully
    2  — input validation failure (schema, hash mismatch, missing files)
    3  — environment failure (GK_TOKEN_SECRET missing or too short)
    4  — internal error
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

# ----- Locked constants (must match schemas/gate_token.schema.json) ----------

GATE_OPERATOR = ">"
GATE_THRESHOLD = 9.5
GATE_SCOPE = "every_dimension"
AGENT_ID = "agent.gatekeeper"
AGENT_VERSION = "1.1.0"
SIGNATURE_PREFIX = "GK1."
DIMENSIONS = ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10")

# Slug regex per docs/00_DECISIONS.md §D-8. Enforced at sign time (v1.4.2 D-16).
SLUG_RE = re.compile(r"^LYNAI_[A-Z0-9_]+_[0-9]{8}_v[0-9]+$")

# Locate scorecard schema for v1.4.2 schema-validation hardening (D-16)
_SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
_SCORECARD_SCHEMA_PATH = _SCHEMAS_DIR / "scorecard.schema.json"


def _load_scorecard_schema() -> dict | None:
    """Load the scorecard JSON schema if available + jsonschema is installed."""
    if not HAS_JSONSCHEMA:
        return None
    if not _SCORECARD_SCHEMA_PATH.exists():
        return None
    try:
        return json.loads(_SCORECARD_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _check_score_increments(scorecard: dict, increment: float = 0.1, tol: float = 1e-9) -> tuple[bool, str]:
    """Custom 0.1-multiple check using float-tolerance.

    Why this exists: jsonschema's native `multipleOf: 0.1` uses IEEE 754 math,
    which rejects legitimate 9.6 (stored as 9.5999...) AND 9.591 alike. We do
    the math ourselves with tolerance so 9.6 passes and 9.591 fails — which is
    the v1.4.2 D-16 hardening intent (catch sub-precision red-team probe).
    """
    for d, entry in scorecard.get("dimensions", {}).items():
        s = entry.get("score")
        if not isinstance(s, (int, float)):
            return False, f"INVALID_SCORE_TYPE at dimensions.{d}.score"
        scaled = s / increment
        rounded = round(scaled)
        # The legitimate 0.1-multiple test, tolerant of IEEE 754 artifacts
        if abs(scaled - rounded) > tol:
            return False, f"SUB_PRECISION at dimensions.{d}.score: {s} is not a clean multiple of 0.1"
    return True, "score_increments_ok"


def _schema_validate_scorecard(scorecard: dict) -> tuple[bool, str]:
    """Validate scorecard against schemas/scorecard.schema.json (v1.4.2 D-16).

    Two-stage validation:
      1. Structural via jsonschema (required fields, types, enums, minLength, etc.)
         — but `multipleOf: 0.1` on score is REMOVED at runtime to avoid IEEE 754
         false negatives. See gate-removal logic below.
      2. Custom score-increment check (`_check_score_increments`) does the
         multipleOf-0.1 logic with float tolerance, so 9.6 passes and 9.591 fails.

    Returns (ok, reason). When jsonschema or the schema file is unavailable,
    returns (True, "schema_check_skipped") — the gate still operates but the
    operator MUST install jsonschema in production for the full defense to
    take effect.
    """
    schema = _load_scorecard_schema()
    if schema is None:
        return True, "schema_check_skipped"

    # Strip the multipleOf:0.1 constraint at runtime to avoid IEEE 754 issues.
    # We'll do the check ourselves below with tolerance.
    import copy
    schema_runtime = copy.deepcopy(schema)
    defs = schema_runtime.get("$defs", {})
    if "dimension_entry" in defs:
        score_prop = defs["dimension_entry"].get("properties", {}).get("score", {})
        score_prop.pop("multipleOf", None)

    try:
        jsonschema.validate(scorecard, schema_runtime)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) or "<root>"
        return False, f"SCHEMA_INVALID at {path}: {e.message[:200]}"
    except Exception as e:
        return False, f"SCHEMA_VALIDATION_FAILED: {type(e).__name__}: {str(e)[:200]}"

    # Custom 0.1-multiple check (tolerance-aware, catches red-team C1: 9.591)
    ok, reason = _check_score_increments(scorecard)
    if not ok:
        return False, f"SCHEMA_INVALID: {reason}"

    return True, "schema_ok"


# ----- Pure helpers ----------------------------------------------------------

def sha256_file(path: str | Path) -> str:
    """SHA-256 of file bytes, prefixed 'sha256:'."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def gate_decision(scores: dict[str, float], cycle: int, cycle_cap: int) -> str:
    """
    Apply the locked gate rule.

    >>> gate_decision({"R1": 9.6, "R2": 9.7, "R3": 9.6, "R4": 9.6, "R5": 9.8, \
                      "R6": 9.7, "R7": 9.6, "R8": 9.6, "R9": 9.6, "R10": 9.7}, 2, 5)
    'PASS'
    >>> gate_decision({"R1": 9.5, "R2": 9.7, "R3": 9.6, "R4": 9.6, "R5": 9.8, \
                      "R6": 9.7, "R7": 9.6, "R8": 9.6, "R9": 9.6, "R10": 9.7}, 2, 5)
    'REVISE'
    >>> gate_decision({"R1": 9.5, "R2": 9.7, "R3": 9.6, "R4": 9.6, "R5": 9.8, \
                      "R6": 9.7, "R7": 9.6, "R8": 9.6, "R9": 9.6, "R10": 9.7}, 5, 5)
    'DELIVER_WITH_SHORTFALL'
    """
    if all(s > GATE_THRESHOLD for s in scores.values()):
        return "PASS"
    if cycle >= cycle_cap:
        return "DELIVER_WITH_SHORTFALL"
    return "REVISE"


def compute_signature(token_id: str, draft_content_hash: str, decision: str, secret: str) -> str:
    msg = f"{token_id}||{draft_content_hash}||{decision}".encode("utf-8")
    key = secret.encode("utf-8")
    digest = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{digest}"


def verify_signature(token: dict[str, Any], secret: str) -> bool:
    expected = compute_signature(
        token["token_id"], token["draft_content_hash"], token["decision"], secret
    )
    # Constant-time compare to avoid timing attacks
    return hmac.compare_digest(expected, token.get("signature", ""))


def build_token_id(slug: str, draft_revision: int) -> str:
    slug_hash = hashlib.sha256(slug.encode("utf-8")).hexdigest()[:8].upper()
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"GT-{slug_hash}-{date_str}-{draft_revision}"


def compose_shortfall_note(scores: dict[str, float], dim_rationales: dict[str, str]) -> str:
    failing = [(d, scores[d], dim_rationales.get(d, "")) for d in DIMENSIONS if scores[d] <= GATE_THRESHOLD]
    if not failing:
        return ""
    lines = ["Cycle cap reached. The following dimensions did not converge above 9.5:"]
    for dim, score, rationale in failing:
        lines.append(f"  {dim} = {score:.1f}: {rationale}")
    lines.append("")
    lines.append("Remediation options: provide additional primary source data, narrow the scope of the report, or accept a 'data-light' delivery with this shortfall note as the second section of the .docx.")
    return "\n".join(lines)


# ----- Main token construction ----------------------------------------------

def _emit_revise_token(token_id: str, live_hash: str, scorecard_path: Path,
                       shortfall: str, secret: str, cycle: int) -> dict[str, Any]:
    """Build a fully-signed REVISE token for the defense-in-depth bailout path (v1.4.2 D-16)."""
    token: dict[str, Any] = {
        "version": "1.1",
        "token_id": token_id,
        "issued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "issuer": {"agent_id": AGENT_ID, "agent_version": AGENT_VERSION},
        "draft_revision": cycle,
        "draft_content_hash": live_hash,
        "scorecard_ref": {"path": str(scorecard_path), "hash": sha256_file(scorecard_path)},
        "decision": "REVISE",
        "rule_applied": {"operator": GATE_OPERATOR, "threshold": GATE_THRESHOLD, "scope": GATE_SCOPE},
        "min_dim_score": 0.0,
        "min_dim_id": "R1",
        "shortfall_note": shortfall,
        "signature": "PENDING",
    }
    token["signature"] = compute_signature(token_id, live_hash, "REVISE", secret)
    return token


def build_token(
    scorecard_path: Path,
    draft_path: Path,
    cycle: int,
    cycle_cap: int,
    slug: str,
    secret: str,
) -> dict[str, Any]:
    # ----- v1.4.2 D-16 P0-3: validate slug regex before signing -----
    if not SLUG_RE.match(slug):
        # Slug is part of the token_id and downstream filenames; reject early.
        # Return a poisoned token that Producer's pre-flight will reject anyway.
        raise ValueError(f"INVALID_SLUG: '{slug}' does not match {SLUG_RE.pattern}")

    with open(scorecard_path) as f:
        scorecard = json.load(f)

    # ----- v1.4.2 D-16 P0-1: schema-validate scorecard before consuming -----
    schema_ok, schema_reason = _schema_validate_scorecard(scorecard)
    if not schema_ok:
        # Force REVISE — malformed scorecard cannot be honored.
        decision = "REVISE"
        shortfall = f"Scorecard schema validation failed: {schema_reason}"
        scores = {d: 0.0 for d in DIMENSIONS}  # neutralized
        live_hash = sha256_file(draft_path)
    else:
        # 1. Hash-rebind: scorecard's draft_content_hash must match current draft
        live_hash = sha256_file(draft_path)
        if live_hash != scorecard.get("draft_content_hash"):
            # Force REVISE — draft was edited after scoring
            decision = "REVISE"
            shortfall = "Draft content hash mismatch — draft was edited after scoring."
            scores = {d: 0.0 for d in DIMENSIONS}  # neutralized
        else:
            # 2. Pull scores (safe — schema-validated and hash-bound)
            try:
                scores = {d: scorecard["dimensions"][d]["score"] for d in DIMENSIONS}
            except KeyError as e:
                # Should be caught by schema validation, but defense-in-depth
                decision = "REVISE"
                shortfall = f"Scorecard incomplete (missing dimension): {e}"
                scores = {d: 0.0 for d in DIMENSIONS}
                token_id_fallback = build_token_id(slug, cycle)
                return _emit_revise_token(
                    token_id_fallback, live_hash, scorecard_path, shortfall, secret, cycle
                )
            # 3. Apply gate rule
            decision = gate_decision(scores, cycle, cycle_cap)
            # 4. Compose shortfall note if needed
            rationales = {d: scorecard["dimensions"][d]["anchor_rationale"] for d in DIMENSIONS}
            shortfall = compose_shortfall_note(scores, rationales) if decision == "DELIVER_WITH_SHORTFALL" else ""

    # 5. Token assembly
    token_id = build_token_id(slug, cycle)
    min_dim_id = min(DIMENSIONS, key=lambda d: scores[d])
    min_dim_score = scores[min_dim_id]

    token: dict[str, Any] = {
        "version": "1.1",
        "token_id": token_id,
        "issued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "issuer": {"agent_id": AGENT_ID, "agent_version": AGENT_VERSION},
        "draft_revision": cycle,
        "draft_content_hash": live_hash,
        "scorecard_ref": {
            "path": str(scorecard_path),
            "hash": sha256_file(scorecard_path),
        },
        "decision": decision,
        "rule_applied": {
            "operator": GATE_OPERATOR,
            "threshold": GATE_THRESHOLD,
            "scope": GATE_SCOPE,
        },
        "min_dim_score": min_dim_score,
        "min_dim_id": min_dim_id,
        "signature": "PENDING",  # filled below
    }
    if shortfall:
        token["shortfall_note"] = shortfall

    # 6. Sign
    token["signature"] = compute_signature(token_id, live_hash, decision, secret)
    return token


def verify_token(token: dict[str, Any], draft_path: Path, secret: str) -> tuple[bool, str]:
    """
    Producer-side verification. Returns (ok, reason).
    """
    # Rule echo
    rule = token.get("rule_applied", {})
    if not (rule.get("operator") == GATE_OPERATOR
            and float(rule.get("threshold", 0)) == GATE_THRESHOLD
            and rule.get("scope") == GATE_SCOPE):
        return False, "RULE_MISMATCH"

    # Hash rebind
    live_hash = sha256_file(draft_path)
    if live_hash != token.get("draft_content_hash"):
        return False, "HASH_MISMATCH"

    # Signature
    if not verify_signature(token, secret):
        return False, "SIGNATURE_INVALID"

    # Decision must authorize build
    if token.get("decision") not in ("PASS", "DELIVER_WITH_SHORTFALL"):
        return False, "DECISION_NOT_AUTHORIZING_BUILD"
    if token.get("decision") == "DELIVER_WITH_SHORTFALL" and not token.get("shortfall_note"):
        return False, "SHORTFALL_NOTE_MISSING"

    return True, "OK"


# ----- CLI -------------------------------------------------------------------

def _require_secret() -> str:
    secret = os.environ.get("GK_TOKEN_SECRET", "")
    if len(secret) < 32:
        print("FATAL: GK_TOKEN_SECRET env var must be set to a 32+ char hex string.", file=sys.stderr)
        sys.exit(3)
    return secret


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LynAI Gate-Keeper deterministic core")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_sign = sub.add_parser("sign", help="Build and sign a gate_token from a scorecard")
    p_sign.add_argument("--scorecard", required=True, type=Path)
    p_sign.add_argument("--draft", required=True, type=Path)
    p_sign.add_argument("--cycle", required=True, type=int)
    p_sign.add_argument("--cycle-cap", type=int, default=5)
    p_sign.add_argument("--slug", required=True)
    p_sign.add_argument("--out", required=True, type=Path)

    p_verify = sub.add_parser("verify", help="Producer-side token verification")
    p_verify.add_argument("--token", required=True, type=Path)
    p_verify.add_argument("--draft", required=True, type=Path)

    args = p.parse_args(argv)
    secret = _require_secret()

    if args.cmd == "sign":
        for path in (args.scorecard, args.draft):
            if not path.exists():
                print(f"FATAL: missing input {path}", file=sys.stderr)
                return 2
        try:
            token = build_token(
                scorecard_path=args.scorecard,
                draft_path=args.draft,
                cycle=args.cycle,
                cycle_cap=args.cycle_cap,
                slug=args.slug,
                secret=secret,
            )
        except ValueError as e:
            # v1.4.2 D-16 P0-3: invalid slug etc.
            print(f"FATAL: {e}", file=sys.stderr)
            return 2
        args.out.write_text(json.dumps(token, indent=2))
        print(f"[ok] gate_token written to {args.out} (decision: {token['decision']})")
        return 0

    if args.cmd == "verify":
        with open(args.token) as f:
            token = json.load(f)
        ok, reason = verify_token(token, args.draft, secret)
        if ok:
            print(f"[ok] token verified (decision: {token['decision']})")
            return 0
        print(f"[fail] {reason}", file=sys.stderr)
        return 2

    return 4


if __name__ == "__main__":
    sys.exit(main())
