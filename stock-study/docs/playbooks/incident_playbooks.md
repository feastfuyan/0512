# Incident Playbooks · IP-1 through IP-5

Five named scenarios. When one triggers in production, follow its playbook step-by-step. Update `incidents` table when resolved.

---

## IP-1 · Data source failure (Yahoo / LBMA / LME unavailable)

**Owner**: 罗阳
**Detection signals**:
- `data-pipeline` retries exhausted (3 attempts in 10s window)
- Source SLA drops below 95% in a 30-min window
- Grafana `data_freshness_seconds{source=...} > 600`

**Immediate (0–5 min)**:
1. Slack `#stockstudy-v32` `@罗阳`
2. Switch to fallback provider (Yahoo → Alpha Vantage, LBMA → LME daily snapshot)
3. Mark batch `stale_warning=True` in `DataResponse`

**Mitigation (5–30 min)**:
- Investigate provider status page; if confirmed widespread, write provider-side incident
- If only one ticker affected, mark `is_delisted` or `is_in_trading_halt`

**If pre-market window closes (within 1.5h before ASX open) and source still down**:
- Skip today's daily run for the affected subset
- Push incident memo to Slack with explicit "stale data, no publish" note
- Do NOT use Agent-XT-Reasoner to "fill in" missing data — that's hallucination

**Post-incident**: write `incidents` row with `incident_type='IP-1'`, populate `payload_json` with source/duration/affected_tickers.

---

## IP-2 · Agent-XT-Reasoner narrative quality collapse

**Owner**: 陈夏童
**Detection signals**:
- Sentinel advisory `severity=high` warnings spike (>3 in a day)
- Manual spot-check finds nonsense (e.g. wrong facts, wrong factor refs)
- `make test-golden` fails on regression suite

**Immediate (0–5 min)**:
1. `make rollback PROMPT=agent_xt_reasoner@v1.0.0` (rollback to last stable)
2. Today's narrative degrades to template-based — Tier 1 numbers still publish
3. Mark artifact with "Narrative degraded mode"

**Mitigation (5–60 min)**:
- Check what changed: was a new prompt pinned? did the model endpoint shift? is a tool returning corrupted data?
- 张涛 + 陈夏童 pair-debug; check OTel trace for the bad runs
- If the cause is a tool returning bad data, fix Tier 1 first, then test A1

**If pre-market and not yet fixed**:
- Tier 1 numbers still publish — they have value standalone
- Narrative section replaced with: "Daily narrative temporarily unavailable due to quality regression. Numbers below are produced by deterministic Tier 1 pipeline."

**Post-incident**: write `incidents` row, link the offending prompt commit hash.

---

## IP-3 · Prompt Injection critical hit

**Owner**: 杜慧仪
**Detection signals**:
- `safety_blocks_total{severity="critical"}` increases
- Prometheus alert `AnyCriticalSafetyBlock` pages 杜慧仪 immediately

**Immediate (0–5 min)**:
1. `incidents` row auto-written by `sanitizer._write_incident`; verify it's there
2. Slack `@杜慧仪`; if no acknowledgement in 10 min, escalate to 王选策
3. Pull the sanitised payload sample, identify the source (which news feed? which PDF? which user?)
4. **Do not block downstream** — the sanitizer already redacted; the run continues

**Mitigation (5–60 min)**:
- Within 24h, 杜慧仪 updates `safety/patterns/pi_patterns.yaml` with new patterns if needed
- Add the case to `tests/adversarial/pi_*.py`
- Re-run `make test-adversarial` to confirm new patterns capture it

**If it's a novel attack vector** (not covered by any existing pattern category):
- Schedule a red-team review session with 张涛 within 48h
- Consider adding a new pattern category to YAML

**Post-incident**: incident row resolved when (a) new pytest case added, (b) PR merged.

---

## IP-4 · BudgetGuard breach (monthly ≥80% or daily ≥$5)

**Owner**: 张涛
**Detection signals**:
- Grafana cost dashboard red
- `BudgetGuard` raises `BudgetExceeded` (or `degrade_mode` flag flips)

**Immediate (0–5 min)**:
1. Slack `#cost-alerts`
2. Confirm degrade mode is active (no ad-hoc Agent traffic accepted)
3. Verify: is this real spend, or a metric bug?

**Mitigation (5–60 min)**:
- Query `agent_calls` table: which agent / which model / which prompt version is the spend coming from?
- Common causes: (a) prompt got longer; (b) tool loop not terminating; (c) traffic spike
- If a runaway loop is detected, kill switch: `STOCKSTUDY_DRY_RUN=true`

**If monthly limit hit**:
- All LLM-using daily runs pause
- Tier 1 still publishes (the numbers, sans narrative)
- 王选策 must approve top-up before LLM calls resume

**Post-incident**: write incident row with cause + adjusted spec; revise `.env` budget if structurally bigger.

---

## IP-5 · Honey sim-to-real gap > 0.1

**Owner**: 张涛
**Detection signals**:
- `monthly_evolve` flow aborts at step 1 (health check)
- `tier3.tools.honey.health_check()` returns Wasserstein > 0.1

**Immediate (0–5 min)**:
- Agent-ZT-Evolver does NOT run this month
- Switch to manual challenger nomination (陈夏童 + 张涛 propose by hand)
- Push memo to `#stockstudy-v32`

**Mitigation (multi-day)**:
- 张涛 debugs Honey: which scenario class is drifting? commodity price model? liquidity model? volatility?
- Recalibrate Honey on the most recent 12 months
- Re-test on the 5 historic regimes before re-enabling

**No effect on daily run** — Agent-ZT-Evolver is asynchronous.

**Post-incident**: write incident row with Wasserstein delta + which scenario classes failed.

---

*last reviewed: 2026-05-25 · 杜慧仪 + 张涛 + Xuan-Ce*
