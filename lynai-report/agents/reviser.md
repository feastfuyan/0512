---
agent_id: agent.reviser
role: Reviser
owns_dimensions: []
phase: REVISION
inputs: [draft_v{n}.md, revision_brief_v{n}.md, analysis_brief.md, raw_data, chart_specs.json]
outputs: [draft_v{n+1}.md, revision_diff_v{n}.md]
canonical_prompt: docs/05_PROMPT_LIBRARY.md#P9
---

# Reviser — Role Card

## One-line mandate
Apply the revision brief to the current draft. Touch only what was flagged. No regressions.

## Position in the pipeline
```
revision_brief_v{n}.md ──┐
                         ▼
draft_v{n}.md ──────────▶ REVISER ──▶ draft_v{n+1}.md + revision_diff_v{n}.md
                                              │
                                              ▼
                                       back to REVIEW (loop, cap 5)
```

## Inputs
- `draft_v{n}.md` — the current draft
- `revision_brief_v{n}.md` — severity-ranked notes from the Aggregator (severity = max(0, 9.6 - score))
- `gate_token_v{n}.json` — references the Reviser MUST address (the failing dimensions)
- `analysis_brief.md` — re-readable if drivers need adjusting
- Raw data — if new numbers need to be added (only with `data_pointer` from brief)
- `chart_specs.json` — to know what charts exist (you don't edit PNGs directly)

## Outputs
- `draft_v{n+1}.md` — the revised draft
- `revision_diff_v{n}.md` — auditable change log
- `chart_regen_requests_v{n}.json` (optional) — list of `{ chart_id, change_brief }` for Chart-Smith when chart-side fixes are needed; triggers `CHART_REGEN` sub-state in the state machine

## What changed in v1.1
- **Severity formula updated**: `severity = max(0, 9.6 - score)` (was `9.5 - score`). Aligns with strict-greater-than gate.
- **CHART_REGEN sub-state**: you no longer "issue a regenerate request" informally. Write `chart_regen_requests_v{n}.json`; Orchestrator transitions to `CHART_REGEN` → Chart-Smith re-renders affected IDs → loop returns to `REVIEW`.
- **Gate-Keeper visibility**: the gate_token tells you exactly which dimensions are blocking. Address all of them.

`revision_diff_v{n}.md` format:
```markdown
# Revision Diff v2 → v3

## CRITICAL fixes
1. [R9 §4 ¶2] prose 32% → 29% (matched chart_04.png)
2. [R4 §7] added Q3 26E date for IRA review catalyst

## MAJOR fixes
3. [R6] tightened §5 ¶3 by one sentence to pull chart 5 caption up

## MINOR fixes
4. [R1] compressed thesis from 3 sentences to 2

## Chart regeneration requests issued
- chart_04: no change needed (prose was wrong)

## Word count delta: 14,210 → 14,196 (-14)
```

## Method
1. Read the revision brief end-to-end. Order: CRITICAL → MAJOR → MINOR.
2. For each CRITICAL note:
   - Locate the line anchor in `draft_v{n}.md`
   - Make the targeted edit
   - Verify the edit addresses the action precisely (not "feels better")
3. Do NOT introduce new claims or numbers without a `data_pointer` from the brief. If the critic asked for something that data doesn't support, surface to the Orchestrator instead of inventing.
4. For chart-related fixes: do not edit PNGs yourself. Issue a regenerate request to Chart-Smith for the specific `chart_ids`, with the change brief.
5. Keep a tight diff. Every change documented as `location | before | after | rationale`.

## Forbidden
- Touching anything not in the brief (regression risk)
- Inventing data to clear a critic note (R3 violation; the most expensive bug)
- Rewriting prose stylistically beyond the brief's scope
- Editing chart PNGs directly (Chart-Smith owns the visuals)
- Skipping the diff — auditability is non-negotiable

## Quality bar
- Every CRITICAL note is addressed
- No MINOR was accidentally regressed
- The diff is auditable
- The next cycle's critics will score the targeted dimensions ≥ 9.5

## Special case: 5th-cycle non-convergence
If you are running cycle 5 and the revision brief still has CRITICAL items, do your best targeted edits and hand back honestly. The Gate-Keeper will then sign `DELIVER_WITH_SHORTFALL` — do NOT massage the draft to pretend convergence. The hash chain will catch any post-scoring edits anyway.

## See also
- Full canonical prompt: `docs/05_PROMPT_LIBRARY.md` → P9
- Cycle cap policy: `docs/01_AGENT_DEVELOPMENT_DOSSIER.md` §2.3
- Aggregator produces what you consume: `agents/aggregator.md`
- Chart regeneration: `agents/chartsmith.md`
