# ADR-0002 · Prompt Versioning via Git + Semver + Registry

**Status**: Accepted (2026-05-25)
**Decider**: 王选策, 张涛

## Context

LLM behaviour is deterministic-ish for a given (model, prompt, input). When the prompt drifts, downstream metrics drift. Without versioning, we cannot diagnose IC regressions, cannot A/B test, cannot rollback in <30s when a prompt change breaks production.

## Decision

1. **Prompts live in Git as markdown** under `prompts/<agent_key>/v<MAJOR>.<MINOR>.<PATCH>.md`.
2. **Semver rules**:
   - major: SCOPE / persona / output contract change
   - minor: new tool added / hard constraint added (behaviour may change)
   - patch: typo / wording polish only (no semantic change)
3. **Production pin**: `prompts/registry.yaml` `production.<agent_key>` declares the live version.
4. **Every LLM call traces `prompt_version`** in its OTel span (D4).
5. **Rollback**: change one line in `registry.yaml`, restart Prefect agent. RTO ≤ 30s.
6. **Promotion gate**: production pin change requires PR + Champion-Challenger evidence + CEO sign-off (D10).

## Consequences

**Positive**
- Bisectability: every IC drop can be tied to a specific prompt commit
- A/B framework: register `shadow.<agent_key>: vN.M.X-rc1` and route 10% of traffic
- Audit trail: `registry.yaml::history` keeps timestamped record of every pin
- No more "what prompt was running on Tuesday" mystery

**Negative**
- Forces discipline on every prompt change (cannot edit in-place)
- Adds a small amount of registry-yaml-tending work

## Alternatives Considered

1. **Inline prompts as Python f-strings** — rejected (no semver, no audit, no rollback)
2. **Database-backed prompt store** — rejected (no Git history, harder to review in PR)
3. **OpenAI's Prompt Library API** — rejected (vendor lock-in, not GA)

## References

- `prompts/registry.yaml`
- `tier2/base_agent.py::load_pinned_prompt`
- `README.md` D8
