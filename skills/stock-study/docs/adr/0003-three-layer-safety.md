# ADR-0003 · Three-Layer Prompt Injection Defence

**Status**: Accepted (2026-05-25)
**Decider**: 杜慧仪, 王选策
**Severity**: P0 — non-negotiable

## Context

v3.0 audit P0-3: "No mention of prompt injection, adversarial inputs, data poisoning, or jailbreak defence in 44 pages of spec." This is a regulatory / reputational risk that cannot be papered over. Anthropic explicitly lists prompt injection as the #1 attack surface for agent systems.

## Decision

Defence in depth via three layers, **all three required, none can be skipped**:

### Layer 1 — Input Sanitizer (`safety/sanitizer.py`)

- Every external text destined for an LLM context passes through `InputSanitizer.scan()` first.
- Pattern library in `safety/patterns/pi_patterns.yaml` (28 critical + 2 high + 2 medium + 4 unicode patterns as of v1.0).
- critical / high → `safe=False`, redact + incident.
- medium → pass-through with escaping, log only.

### Layer 2 — Tool Input Guard (`safety/tool_guard.py`)

- Every Agent tool call has a Pydantic input schema.
- Args validated before dispatch.
- Long string fields from external sources (news_feed / pdf_extract / social_media / kg_query / user_input) are deep-scanned.
- Sensitive fields (ticker, asof) format-validated.

### Layer 3 — Output Deterministic Gate (`safety/output_gate.py`)

- **LLM has no override**. Rule-based.
- Hard blocks: Restricted Issuer / Banned Phrase / Missing Disclaimer / DRY_RUN kill-switch.
- LLM-based Compliance-Sentinel runs *in parallel* as advisory only (D7).

### Test coverage

50 adversarial pytest cases in `tests/adversarial/`. CI must pass 100% — any FAIL blocks PR merge.

## Consequences

**Positive**
- Industry-standard defence (Anthropic, OpenAI both recommend this layering)
- Restricted Issuer list is the only place compliance team needs to maintain to block a stock
- Test-driven: 50 cases provide regression coverage
- BiDi / zero-width / Unicode tag attacks covered explicitly

**Negative**
- Pattern library needs quarterly maintenance (杜慧仪 owns)
- Some legitimate research narrative may false-positive (target: ≤5%)

## Pattern severity meaning

| Severity | `safe` | Action | Where decided |
|---|---|---|---|
| critical | False | Redact + incident | Layer 1 |
| high | False | Redact + log | Layer 1 |
| medium | True | Escape + log | Layer 1, but Layer 2 still blocks for external sources |
| low | True | No-op | — |

## Alternatives Considered

1. **LLM-only "guard model"** — rejected (D7: LLM is never the final arbiter; classifier models can be jailbroken too)
2. **Single-layer regex** — rejected (no defence in depth; one missed pattern = breach)
3. **Allowlist input** — rejected (impossible for natural-language research input)

## References

- `safety/sanitizer.py`, `safety/tool_guard.py`, `safety/output_gate.py`
- `safety/patterns/pi_patterns.yaml`
- `tests/adversarial/*.py` (50 cases)
- `README.md` D6, D7
- Anthropic, *Defending against indirect prompt injection*
