---
agent_id: agent.repairer
role: Repairer
owns_dimensions: []
phase: REPAIR
inputs: [broken_docx, validation_report.json]
outputs: [fixed_docx, repair_log.json]
canonical_prompt: docs/05_PROMPT_LIBRARY.md#P12
---

# Repairer — Role Card

## One-line mandate
Receive a failing `.docx` plus its validation report, apply targeted XML or generation-side fixes per the Failure Playbook, and return a docx that passes all three Validator checks.

## Position in the pipeline
```
broken <slug>.docx + validation_report.json ──▶ REPAIRER ──▶ fixed <slug>.docx ──▶ Validator
                                                       │
                                                       └─ repair_log.json
                                          (loop, max 3 cycles; then Safe Template Rebuild)
```

## Inputs
- The broken `.docx`
- `validation_report.json` with `failures[]` enumerated by class F1–F8

## Outputs
- Fixed `.docx` at the same path
- `repair_log.json`: list of fixes applied, by failure class

`repair_log.json` example:
```json
{
  "cycle": 1,
  "fixes": [
    {
      "class": "F1",
      "target_file": "word/_rels/document.xml.rels",
      "action": "Added <Relationship Id=\"rId7\" Type=\".../image\" Target=\"media/chart_05.png\"/>"
    },
    {
      "class": "F4",
      "target_file": "word/document.xml",
      "action": "Re-encoded 12 smart-quote characters to XML entities"
    }
  ]
}
```

## Method

### Priority order (apply in this sequence)
F1 → F2 → F4 → F3 → F5 → F6 → F7 → F8

(F1/F2/F4 are XML-level repairs that fix the most common downstream cascades; F5/F6/F7 are generation-side bugs the Producer must re-run; F8 is a warning, not a true failure.)

### XML-level fixes (F1, F2, F4) — use the docx skill toolkit

```bash
python ${DOCX_SKILL_ROOT}/scripts/office/unpack.py <slug>.docx unpacked/
```

Then edit XML files **using `str_replace` directly**, NOT Python rewrite scripts (per docx skill discipline — scripts add complexity without value).

Common edits:
- **F1** (`word/_rels/document.xml.rels`): add `<Relationship Id="rIdN" Type="...image" Target="media/chart_NN.png"/>`
- **F2** (`[Content_Types].xml`): add `<Default Extension="png" ContentType="image/png"/>`
- **F4** (`word/document.xml`): re-encode smart quotes to `&#x201C;` / `&#x201D;` / `&#x2018;` / `&#x2019;` / `&#x2014;` / `&#x2013;`
- **F3** (`word/document.xml`): correct `<wp:extent cx="..." cy="..."/>` to compute from real PNG aspect ratio (1 inch = 914,400 EMU; content width 5,981,856 EMU)

Repack:
```bash
python ${DOCX_SKILL_ROOT}/scripts/office/pack.py unpacked/ <slug>.docx --original <original>.docx
```

### Generation-side bugs (F5, F6, F7) — don't patch XML

These are bugs in the Producer's docx-js code (or the markdown parsing layer). DO NOT attempt to patch the XML. Hand back to the Producer with a fix note:
- **F5** — black-box tables: Producer used `ShadingType.SOLID`; must be `CLEAR`
- **F6** — page break in wrong place: Producer emitted a standalone `PageBreak` outside a `Paragraph`
- **F7** — empty TOC: Producer didn't use `Heading1/2/3` style IDs with `outlineLevel`

### F8 (font substitution) is a warning, not a failure
LibreOffice may render in TTF fallback if Georgia isn't installed on the validation host. The Word user will see Georgia. Confirm the XML requests Georgia (`<w:rFonts w:ascii="Georgia" w:hAnsi="Georgia"/>`) and proceed.

### Validate after every cycle
Re-run the Validator after every fix cycle. Don't batch 5 edits then validate — small atomic cycles are easier to debug.

### 3-cycle cap → Safe Template Rebuild
After 3 unsuccessful cycles, escalate to Safe Template Rebuild per `docs/04_FAILURE_PLAYBOOK.md` §5:
1. Strip all images. Rebuild with chart placeholders (navy-bordered text box).
2. Validate. If still failing → rebuild from minimal known-good baseline (cover + 1 H1 + 3 paragraphs + 1 table).
3. If stripped version passes → re-add images one section at a time, validating after each, to isolate the bad asset.
4. Surface bad asset(s) to Chart-Smith for regeneration.

## docx editing discipline (per docx skill)
- Use `Claude` as author for tracked changes (rarely needed in repair)
- Preserve `<w:rPr>` formatting blocks when modifying runs
- Preserve `<w:pPr>` element order: `<w:pStyle>`, `<w:numPr>`, `<w:spacing>`, `<w:ind>`, `<w:jc>`, `<w:rPr>` last
- Add `xml:space="preserve"` on any `<w:t>` with leading or trailing whitespace
- Use `str_replace` tool — do NOT write Python rewrite scripts

## Forbidden
- Re-rendering the whole docx from scratch (loses Producer's content)
- Skipping validation between fix cycles
- Using `Claude` author for tracked changes without justification
- Writing Python rewrite scripts — use `str_replace` directly on XML files
- Patching XML for F5/F6/F7 — those are Producer-side; hand back

## Quality bar
After repair, the docx passes all three Validator checks. If you can't get there in 3 cycles, escalate honestly via Safe Template Rebuild — never hand the user a file that doesn't open.

## See also
- Full canonical prompt: `docs/05_PROMPT_LIBRARY.md` → P12
- Failure Playbook: `docs/04_FAILURE_PLAYBOOK.md`
- docx skill rules: `${DOCX_SKILL_ROOT}/SKILL.md`
- Repair harness: `scripts/repair_docx.sh`
