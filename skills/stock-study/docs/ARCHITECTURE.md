# ARCHITECTURE · stock-study-v3.2

Engineering reference. Read once on Day 1; reread when adding a new component.

For business context / sprint plan see `KICKOFF.md`. For ADRs see `docs/adr/`. For runbook see `docs/playbooks/`.

---

## §1 Three Tiers

```
Tier 1 (Deterministic Workflow)
  C1 data-pipeline     →  C2 factor-engine  →  C3 backtest-scorer
                                                       ↓
                            C4 risk-alert       (scores + alerts + regime)
                                                       ↓
Tier 2 (LLM-augmented step, 1 call inside the DAG)
                       A1 Agent-XT-Reasoner       ← prompt v1.0.0
                                                       ↓ narrative
                       C6 safety-gate (deterministic 3-layer)
                                                       ↓ if allowed
                       A2 Compliance-Sentinel (advisory only)
                                                       ↓
                            PUBLISH (Slack + Excel + API)

Tier 3 (True Agents, async, off the daily critical path)
  A3 Agent-ZT-Evolver  — monthly, prompt v1.0.0, Opus
  A1.adhoc             — ad-hoc chat entry point (CEO / 陈夏童)
```

Why Tier separation matters: a Tier 1 component failing must not cause an LLM to hallucinate a "fallback". Each Tier has its own SLO, owner, and quality bar.

## §2 Nine Locked Components

| # | Name | Tier | Owner | SLO |
|---|---|---|---|---|
| C1 | data-pipeline | T1 | 罗阳 | success 99.5%, freshness p95 ≤ 90s |
| C2 | factor-engine | T1 | 陈夏童 | success 99.9%, IC ≥ 0.06 (4-week roll) |
| C3 | backtest-scorer | T1 | 陈夏童 | Brier ≤ 0.22, reliability gap ≤ 5pp |
| C4 | risk-alert | T1 | 陈夏童 | short-side accuracy ≥ 60% |
| C5 | excel-renderer | T1 | 付岩 | p95 ≤ 10s, template back-compat |
| C6 | safety-gate | T1 | 杜慧仪 | PI capture 100% (50 cases) |
| A1 | Agent-XT-Reasoner | T2 | 陈夏童 | narrative human score ≥ 4.0/5, latency ≤ 30s, cost ≤ $0.20/call |
| A2 | Compliance-Sentinel | T2 | 杜慧仪 | false-positive ≤ 5%, latency ≤ 5s |
| A3 | Agent-ZT-Evolver | T3 | 张涛 | monthly ≥ 1 challenger proposal, sim-real Wasserstein ≤ 0.1 |

Adding a 10th component requires an ADR + PR review + CEO sign-off.

## §3 Data flow contracts (Pydantic v2)

All cross-component contracts live in `schemas/`. Do not invent new dataclasses for cross-component data.

| From → To | Contract type |
|---|---|
| C1 → C2 | `DataResponse` (one per ticker per asof) |
| C2 → C3 | `FactorVector` |
| C3 → C5 / A1 | `StockScore` (`label`, `target_p20/central/p80`, `attribution`) |
| C4 → C5 / A1 | `RiskAlert` |
| A1 → C6 / Publish | `NarrativeResult` |
| C5 → OutputGate | `PublishArtifactModel` |
| A2 → OutputGate (advisory) | `ComplianceWarningList` |
| Workflow → A1 | `NarrativeTask` |
| Workflow → A2 | `SentinelTask` |

## §4 Safety stack (three layers, all required)

```
External text
     ↓
Layer 1: InputSanitizer (regex + Unicode normalize, 28 critical patterns)
     ↓                                ↘ critical/high → redact + incident
Agent context
     ↓
Layer 2: ToolInputGuard (Pydantic schema + scan strings ≥30 chars from external sources)
     ↓                                ↘ raise InjectionDetected
Tool dispatch
     ↓
Agent output
     ↓
Layer 3: OutputGate (RULE-BASED, deterministic, LLM has no override)
   - Restricted Issuer  → block
   - Banned Phrase      → block
   - Missing Disclaimer → block
   - DRY_RUN kill-switch → block
     ↓
Publish + (advisory) Compliance-Sentinel notes attached
```

See ADR-0003 for rationale. See `tests/adversarial/` for 50 regression cases.

## §5 Observability

| Layer | Tool | What it captures |
|---|---|---|
| Traces | OpenTelemetry → Jaeger | every LLM call, every tool dispatch, every DB query |
| Metrics | Prometheus + Grafana | latency, IC/Brier rolling, safety_blocks, compliance_blocks, llm_cost |
| Logs | stdout → Loki (prod) | structured JSON |
| Cost ledger | PostgreSQL `agent_calls` table | per-call cost in USD, append-only |

Every LLM call must record: `agent_id`, `model`, `prompt_version`, `input_tokens`, `output_tokens`, `cost_usd`, `duration_ms`, `stop_reason`, `trace_id`.

## §6 Cost & Budget

| Scope | Limit | Action on breach |
|---|---|---|
| per-call | $0.50 | log + Slack alert |
| per-run | $2.00 | abort run + incident |
| daily | $5.00 | raise `BudgetExceeded` |
| monthly | $120 | raise `BudgetExceeded`, hard stop |
| 80% monthly | (advisory) | auto-enter degrade mode (Sonnet token-cap, no ad-hoc Agent) |

Expected monthly: $65–85 (incl. 20% buffer). Verified via `make budget`.

## §7 Failure handling

Three-stage cascade:

| Stage | Trigger | Action | Window |
|---|---|---|---|
| Retry | 5xx / 429 / timeout | exponential backoff 1s → 2s → 4s, max 3 retries | ≤10s |
| Fallback | retries exhausted | switch provider / degrade output | ≤30s |
| Escalate-sync | pre-market 1.5h window + fallback failed | PagerDuty + phone | 15min response |
| Escalate-async | non-trading-day / non-critical-path | Slack + email + ticket | 24h |

5 playbooks: IP-1 (data source) / IP-2 (narrative quality collapse) / IP-3 (PI critical hit) / IP-4 (budget breach) / IP-5 (Honey sim-real gap). See `docs/playbooks/`.

## §8 Rollback RTO

| Layer | How | RTO |
|---|---|---|
| Prompt | `make rollback PROMPT=agent_xt_reasoner@v1.0.0` | ≤30s |
| Code | `git revert` + CI redeploy | ≤5 min |
| Calibrator | SQL `UPDATE calibrators SET status='archived'...` | ≤10s |
| DB schema | `alembic downgrade -1` | ≤2 min |
| Emergency kill | `STOCKSTUDY_DRY_RUN=true` env var | ≤5s |

## §9 Promotion gates

| Going to | Requires |
|---|---|
| Open PR | ≥5 golden test cases passing locally |
| Merge PR | CI green: `make test-adversarial` 100%, unit + e2e all pass |
| Deploy to shadow | merged + ADR (if architectural) |
| Promote shadow→production | shadow run ≥10 trading days, IC delta ≥ +0.02 vs v2, sentinel false-positive ≤5%, CEO + 杜慧仪 dual sign-off |

## §10 The Constitution (D1–D10)

See README §3. Violating any one rule is grounds to reject a PR.

---

*last updated: 2026-05-25 · Xuan-Ce Wang*
