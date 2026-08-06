# ADR-0001 · Three-Tier Architecture

**Status**: Accepted (2026-05-25)
**Decider**: 王选策 (CEO)
**Owners affected**: 全员

## Context

The v3.0 design wrapped every component as an Agent, leading to: (a) low Necessity score 5/10 in red-team audit, (b) cost estimate exploding ~3× under realistic loads (Anthropic blog: multi-agent ≈ 15× single-agent tokens), (c) hidden failure modes (every step has an LLM in the loop).

Anthropic's *Building Effective Agents* states explicitly: "find the simplest solution possible, and only increase complexity when needed."

## Decision

Adopt a three-tier separation:

| Tier | Purpose | Tooling | Components | LLM? |
|---|---|---|---|---|
| Tier 1 | Deterministic data / compute / render | Python + Prefect + Pandas + sklearn | C1–C5, C6 | No |
| Tier 2 | LLM-augmented single step (1 call inside a workflow) | Anthropic SDK + Pydantic | A1, A2 | 1 call |
| Tier 3 | True agent (multi-step, autonomous) | Anthropic SDK + multi-step tool loop | A3 | Many |

The boundary is enforced: Tier 1 components must not call LLMs. Tier 2/3 must not directly mutate Tier 1 state — they read inputs, return Pydantic objects, downstream code applies.

## Consequences

**Positive**
- Cost down ~75% vs v3.0 estimate (now $65–85/mo)
- Simpler debugging — Tier 1 failures don't trigger LLM hallucinations
- Clear role assignment per Tier
- Easier evaluation (Tier 1 has numerical SLOs; Tier 2/3 use golden datasets)

**Negative**
- Loses the "all-Agent" marketing story (acceptable — engineering credibility outweighs)
- Adds boundary discipline that PR reviews must enforce

**Neutral**
- Forces every LLM call to have an RFC (see ADR-0002 conventions)

## Alternatives Considered

1. **Full Agent mesh (v3.0)** — rejected (cost, complexity, P0/P1 issues in audit)
2. **LangGraph orchestration** — rejected (adds another framework layer with no necessary benefit; we have Prefect)
3. **CrewAI** — rejected (same)
4. **Just one Agent doing everything** — rejected (no clear quality bar, no eval target, hard to debug)

## References

- `docs/ARCHITECTURE.md` §1
- Anthropic, *Building Effective Agents* (2024-12)
- `README.md` D1 (Workflow first, Agent second)
