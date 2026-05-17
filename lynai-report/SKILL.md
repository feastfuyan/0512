---
name: lynai-report
description: "Use this skill whenever the user asks for an institutional-grade research report, equity research note, commodity deep-dive, M&A note, ESG intelligence brief, or any long-form analytical document where the deliverable must read at Goldman Sachs Global Investment Research quality and ship as BOTH a Microsoft Word (.docx) AND a PDF (.pdf) file pair. Triggers include phrases like 'draft a research report on...', 'write an equity research note on...', 'build me a Goldman-style report on...', 'make a deep-dive on...', 'institutional report on...', 'IC paper on...', 'investment memo on...'. Always produces: (1) text + charts + data tables, (2) Goldman Sachs / GeoVision institutional layout with Georgia serif and Navy #0D1F3C / Gold #C9A84C palette, (3) Nature-grade chart visualization, (4) 14-agent peer-review pipeline with an independent Gate-Keeper that enforces a STRICT > 9.5/10 quality gate per dimension (every dimension must score ≥ 9.6), (5) PII / MNPI scan by a dedicated Redactor agent before any file is built, (6) BOTH a validated Word file AND a visually-identical PDF (rendered by LibreOffice headless from the same .docx), delivered as a pair. Do NOT use for short summaries, casual blog posts, email drafts, spreadsheets, or slide decks (use pptx for slides, xlsx for spreadsheets). Do NOT use when the user explicitly wants markdown as the primary deliverable format (markdown is internal-only in v1.2)."
license: Proprietary — LynAI Mines / GeoVision AI Mining
version: "1.4.2"
---

# LynAI Report — Institutional Research Report Generation

This skill produces **publication-ready research reports** at Goldman Sachs Global Investment Research quality, delivered as a **paired Microsoft Word (.docx) + PDF (.pdf)** file set.

## The hard promises (v1.4)

1. **Quality:** Every dimension of every shipped report scores STRICTLY GREATER than 9.5/10 (i.e. ≥ 9.6) — or the report does not ship. The decision is owned by a dedicated `agent.gatekeeper` that issues a cryptographically signed `gate_token`; the Producer refuses to build without it.
2. **Format:** Every shipped job produces BOTH `<slug>.docx` AND `<slug>.pdf` — same content, visually identical, rendered from the same source. Markdown is an internal artifact, never the final deliverable.

See `docs/00_DECISIONS.md` for the locked rules (D-1 through D-11) behind these promises.

## When to use

Trigger this skill for any request matching:
- Equity research notes (single-name or thematic)
- Commodity / market deep-dives
- M&A or transaction memos
- ESG / geopolitical / risk intelligence reports
- IC papers and institutional investment memos

**Required output format:** Microsoft Word (.docx) **paired with** PDF (.pdf). If the user asks for slides instead, route to `pptx`. If the user asks for markdown as the deliverable, explain that v1.2 produces docx+pdf only (markdown is internal-only); offer to convert one of the deliverables back to markdown via pandoc as a post-step if needed.

## What this skill guarantees

1. **Content:** Institutional thesis with falsifiable claims, scenario analysis, data-anchored prose
2. **Layout:** GeoVision / Goldman Sachs house style — Georgia serif body, Navy `#0D1F3C` / Gold `#C9A84C` palette, A4 with 25mm margins
3. **Charts:** Nature / Goldman top-of-mind grammar — single-message titles, no chartjunk, 300 DPI PNG embeds
4. **Hard quality gate:** 3 critics score 10 dimensions; independent Gate-Keeper signs verdict; **every dimension must strictly exceed 9.5** — no rounding, no compensation, no weighting tricks
5. **Confidentiality:** Dedicated Redactor agent scans for PII / MNPI / credentials before build
6. **Dual format:** Every shipped job produces a paired `<slug>.docx` + `<slug>.pdf` — same content, visually identical, rendered by LibreOffice headless from the same authoritative `.docx`
7. **Integrity:** Every .docx is validated and open-tested before delivery; broken files are auto-repaired; PDF is validated for non-zero size and page-count parity with the docx

## High-level workflow (14 agents, 10 states)

```
INTAKE → PLAN → ANALYSIS → CHART_SPEC_READY ───┐
                                                ├──▶ DRAFTING (Drafter + ChartRender parallel)
                                                │
                       ┌──────── REVIEW (3 critics parallel) ◀────────┐
                       │              │                                │
                       ▼              ▼                                │
                AGGREGATOR ──▶ GATE-KEEPER ──REVISE──▶ REVISER ────────┘
                                   │                       │
                                  PASS                     └─▶ optional CHART_REGEN
                                   ▼
                              REDACTOR ──BLOCKED──▶ user escalation
                                   │
                              CLEAR / REDACTED
                                   ▼
                              PRODUCER (.docx) ──▶ VALIDATOR ──FAIL──▶ REPAIRER ─┐
                                                       │                          │
                                                      PASS                        │
                                                       │                          │
                                                       ▼                          │
                                                  DELIVER                         │
                                                       ▲                          │
                                                       └──────────────────────────┘
```

Hard caps: 5 revision cycles, 3 repair cycles. Beyond either → `DELIVER_WITH_SHORTFALL` with explicit note.

## How to run this skill

### Step 1 — Intake
Confirm with the user (ask only if missing):
1. Subject (company / commodity / theme)
2. Audience (IC / external / investor / internal memo)
3. Length target (pages or words)
4. Data source (uploaded files / web search / general knowledge)
5. Bilingual? (EN / CN / EN+CN)
6. Urgency (affects cycle cap)

### Step 2 — Read the locked decisions and the development dossier
**Always read `docs/00_DECISIONS.md` and `docs/01_AGENT_DEVELOPMENT_DOSSIER.md` before drafting.** They contain the gate threshold rule, the rubric anchors, the house style tokens, and the 14-agent topology.

### Step 3 — Set runtime paths (one-time per environment)
The skill reads `templates/runtime_paths.json`. Override defaults via env vars on non-Anthropic runtimes:
```
DOCX_SKILL_ROOT   = path to the public docx skill
LYNAI_OUTPUTS_DIR = where final .docx is written
LYNAI_UPLOADS_DIR = where user-supplied data lives
GK_TOKEN_SECRET   = HMAC secret for gate_token signing (REQUIRED; never use a default)
```

### Step 4 — Run the 14-agent pipeline
Each agent has a role card in `agents/`. Order:

1. **Orchestrator** → produces `plan.json`
2. **Analyst** → produces `analysis_brief.md`
3. **Chart-Smith Phase 1** → produces `chart_specs.json` metadata (findings, IDs, captions) — gate `CHART_SPEC_READY`
4. **Drafter** + **Chart-Smith Phase 2 (render)** in parallel → `draft_v0.md` + `charts/*.png`
5. **Critic-A / Critic-B / Critic-C** in parallel → critic JSONs
6. **Aggregator** → `scorecard_v{n}.json` (aggregation only; no decision)
7. **Gate-Keeper** → `gate_token_v{n}.json` (signed PASS / REVISE / DELIVER_WITH_SHORTFALL)
8. If REVISE: **Reviser** updates draft; optionally invokes **Chart-Smith** for `CHART_REGEN` → loop to step 5 (cap 5)
9. If PASS: **Redactor** → `redaction_report.json`. If REDACTED, Gate-Keeper re-signs against sanitized draft hash. If BLOCKED, escalate to user.
10. **Producer** → builds .docx via `scripts/build_docx.js` (refuses without valid gate_token + CLEAR/REDACTED redaction_report)
11. **Validator** → runs `scripts/validate_docx.sh`
12. If FAIL: **Repairer** → loop to validator (cap 3)
13. Deliver via `present_files`

### Step 5 — Build the .docx (Producer)
Producer reads `templates/runtime_paths.json` to locate the public `docx` skill. **Always read `${DOCX_SKILL_ROOT}/SKILL.md` first** — it carries critical docx-js rules (dual table widths, `ShadingType.CLEAR`, no unicode bullets, PageBreak inside Paragraph).

Use `templates/docx_producer.js` as the starting point. Inject style from `templates/house_style.json`.

### Step 6 — Render PDF + Validate (paired)
The same LibreOffice headless pass that v1.1 used only for validation now renders the **delivered PDF** to `${LYNAI_OUTPUTS_DIR}/<slug>.pdf`:
```bash
# 1. Schema validation (docx XML conformance)
${DOCX_SKILL_ROOT}/scripts/office/validate.py ${LYNAI_OUTPUTS_DIR}/<slug>.docx

# 2. PDF render (this is the DELIVERED pdf, not a temporary)
${DOCX_SKILL_ROOT}/scripts/office/soffice.py --headless \
    --convert-to pdf ${LYNAI_OUTPUTS_DIR}/<slug>.docx \
    --outdir ${LYNAI_OUTPUTS_DIR}

# 3. Asset integrity (cross-platform Python zipfile)
python ${LYNAI_SKILL_ROOT}/scripts/check_assets.py ${LYNAI_OUTPUTS_DIR}/<slug>.docx

# 4. PDF integrity (size > 5 KB, parses, page count ≥ expected)
python ${LYNAI_SKILL_ROOT}/scripts/check_pdf.py ${LYNAI_OUTPUTS_DIR}/<slug>.pdf

# 5. Page-count parity (PDF pages should match expected docx page count from producer_log)
```
If any of 1-4 fail, Repairer takes over (≤ 3 cycles); after 3 cycles, escalate to Safe Template Rebuild.

### Step 7 — Deliver (both files)
Place BOTH `${LYNAI_OUTPUTS_DIR}/<slug>.docx` AND `${LYNAI_OUTPUTS_DIR}/<slug>.pdf` and call `present_files` with both paths. Include the scorecard JSON, gate token JSON, redaction report, and revision log alongside. **Markdown stays in the workdir and is NOT in the outputs directory** (D-11).

## Quality gate — non-negotiable

This skill **never silently ships sub-9.6 content**. If the 5-cycle revision cap is hit without all dimensions strictly exceeding 9.5, deliver the best-scoring intermediate **with an explicit shortfall note** stating which dimensions did not converge and why. Suggest remediation (more data, geologist sign-off, scope reduction).

## What this skill does NOT do

- Generate PowerPoint slides → use `pptx` skill
- Generate Excel models → use `xlsx` skill
- Generate markdown as the primary deliverable → markdown is an internal-only artifact in v1.2 (the user receives `.docx` + `.pdf` only)
- Live data feeds → user must provide data or authorize web search
- Real-time multi-user editing → v1.0 is single-pass with optional tracked-changes review on the roadmap for v1.3

## Reference materials in this skill

| File | Purpose |
|---|---|
| `docs/00_DECISIONS.md` | **Locked rules.** Gate threshold, agent topology, runtime paths, fonts, cover, naming. |
| `docs/01_AGENT_DEVELOPMENT_DOSSIER.md` | Full architecture and rubric anchors |
| `docs/02_RUBRIC_REFERENCE.md` | Anchor descriptions per dimension |
| `docs/03_HOUSE_STYLE_GUIDE.md` | Typography, chart, table grammar |
| `docs/04_FAILURE_PLAYBOOK.md` | Validation and repair runbook |
| `docs/05_PROMPT_LIBRARY.md` | System prompts for each of the 14 agents |
| `docs/06_GATE_CONTRACT.md` | Gate-Keeper protocol and token signing |
| `agents/*.md` | Per-agent role cards (14 cards) |
| `templates/house_style.json` | Color / font / spacing tokens |
| `templates/runtime_paths.json` | Path bindings (env-overridable) |
| `templates/docx_producer.js` | docx-js builder template |
| `templates/chart_style.mplstyle` | matplotlib house style |
| `templates/disclaimers.json` | Compliance footer text (MIFID-II / ASIC) |
| `schemas/*.json` | JSON schemas for every inter-agent contract |

## Critical dependencies

- Public `docx` skill at `${DOCX_SKILL_ROOT}` (default `/mnt/skills/public/docx`)
- `npm install -g docx@^8.5.0 image-size@1.0.2`
- Python 3.10+ with `matplotlib`, `Pillow`, `jsonschema`
- LibreOffice (`soffice`) for open-render validation
- `GK_TOKEN_SECRET` env var set to a 32+ character random string

## Paper-skill integration (v1.4, D-14)

The skill implicitly invokes the locally-installed `paper` skill (`~/.claude/skills/paper/`) at four touchpoints, via dispatcher shims:

| Touchpoint | Script | Agent | Replaces in-house heuristic |
|---|---|---|---|
| Chart rendering (geochem types) | `scripts/chart_factory.py` | Chart-Smith Phase 2 | `render_chart.py` fallback |
| Reference / citation audit | `scripts/ref_check.py` | Critic-C (R10) | Manual review |
| Material extraction (uploads) | `scripts/material_extract.py` | Analyst (pre-step) | File listing by extension |
| Deep-Research validation | `scripts/deep_validate.py` | Critic-A (R3) | Citation-only review |

Each shim degrades gracefully (in-house fallback) if paper skill is absent.

## Versioning

Current: **v1.4.2** (Hard Gate `> 9.5`, 14 agents, env-driven paths, Redactor enabled, dual .docx + .pdf delivery, **python_producer primary path** D-12, **paper visualizer integration** D-13).
See `docs/00_DECISIONS.md` for change control protocol.
