#!/usr/bin/env bash
# repair_docx.sh — LynAI DOCX repair harness
#
# Per the Repairer agent (docs/05_PROMPT_LIBRARY.md P12) and the Failure
# Playbook (docs/04_FAILURE_PLAYBOOK.md §§2-5), this harness:
#
#   1. Unpacks the broken .docx into a working directory
#   2. Reports the failures so the Repairer can apply targeted str_replace edits
#   3. After edits, repacks via the docx skill's pack.py
#   4. Re-runs validation
#
# Crucially, this harness does NOT auto-edit XML. Per the docx skill discipline,
# XML edits must be applied via the `str_replace` tool, not Python rewrite
# scripts. This harness only handles the unpack/repack mechanics.
#
# Usage:
#   ./repair_docx.sh unpack <broken.docx>          → produces unpacked/ next to docx
#   ./repair_docx.sh repack <unpacked/> <broken.docx> <fixed.docx>
#   ./repair_docx.sh cycle <broken.docx>           → unpack + prompt + repack + validate
#
# Repair cycles cap at 3. After 3, the Repairer must invoke Safe Template
# Rebuild manually (Failure Playbook §5).

set -u
set -o pipefail

: "${DOCX_SKILL_ROOT:=/mnt/skills/public/docx}"
DOCX_SKILL_SCRIPTS="${DOCX_SKILL_ROOT}/scripts/office"
UNPACK_PY="${DOCX_SKILL_SCRIPTS}/unpack.py"
PACK_PY="${DOCX_SKILL_SCRIPTS}/pack.py"
VALIDATE_SH="$(dirname "$0")/validate_docx.sh"

for tool in "$UNPACK_PY" "$PACK_PY" "$VALIDATE_SH"; do
  [[ -f "$tool" ]] || { echo "FATAL: missing tool: $tool" >&2; exit 2; }
done

CMD="${1:-}"
case "$CMD" in
  unpack)
    BROKEN="${2:?Usage: $0 unpack <broken.docx>}"
    [[ -f "$BROKEN" ]] || { echo "FATAL: not found: $BROKEN" >&2; exit 2; }
    UNPACK_DIR="${BROKEN%.docx}_unpacked"
    rm -rf "$UNPACK_DIR"
    python3 "$UNPACK_PY" "$BROKEN" "$UNPACK_DIR"
    echo ""
    echo "Unpacked to: $UNPACK_DIR"
    echo ""
    echo "Now apply targeted str_replace edits per the Failure Playbook (§2):"
    echo "  F1 (image rel missing)    → edit  $UNPACK_DIR/word/_rels/document.xml.rels"
    echo "  F2 (ContentType missing)  → edit  $UNPACK_DIR/[Content_Types].xml"
    echo "  F3 (drawing dim wrong)    → edit  $UNPACK_DIR/word/document.xml  (wp:extent EMU)"
    echo "  F4 (smart quote corrupt)  → edit  $UNPACK_DIR/word/document.xml  (re-encode)"
    echo "  F5/F6/F7 are generation-side: hand back to Producer, do not patch XML"
    echo ""
    echo "When done, run:"
    echo "  $0 repack '$UNPACK_DIR' '$BROKEN' '${BROKEN%.docx}_fixed.docx'"
    ;;

  repack)
    UNPACK_DIR="${2:?Usage: $0 repack <unpacked/> <original.docx> <out.docx>}"
    ORIG="${3:?Usage: $0 repack <unpacked/> <original.docx> <out.docx>}"
    OUT="${4:?Usage: $0 repack <unpacked/> <original.docx> <out.docx>}"
    [[ -d "$UNPACK_DIR" ]] || { echo "FATAL: not a dir: $UNPACK_DIR" >&2; exit 2; }
    [[ -f "$ORIG" ]]       || { echo "FATAL: not found: $ORIG" >&2; exit 2; }
    python3 "$PACK_PY" "$UNPACK_DIR" "$OUT" --original "$ORIG"
    echo "Repacked to: $OUT"
    echo ""
    echo "Running validation..."
    "$VALIDATE_SH" "$OUT"
    ;;

  cycle)
    BROKEN="${2:?Usage: $0 cycle <broken.docx>}"
    [[ -f "$BROKEN" ]] || { echo "FATAL: not found: $BROKEN" >&2; exit 2; }
    REPAIR_LOG="${BROKEN%.docx}_repair_log.json"

    # Initial validation to confirm there's something to repair
    "$VALIDATE_SH" "$BROKEN" --report "${BROKEN%.docx}_validation_report.json" || true

    # Cycle loop — manual XML editing happens BETWEEN unpack and repack,
    # via the str_replace tool, so this single-shot wrapper is mostly for
    # operator convenience to scaffold the workdir.
    UNPACK_DIR="${BROKEN%.docx}_unpacked"
    rm -rf "$UNPACK_DIR"
    python3 "$UNPACK_PY" "$BROKEN" "$UNPACK_DIR"

    echo ""
    echo "================================================================"
    echo "Unpacked to: $UNPACK_DIR"
    echo ""
    echo "The Repairer agent should now:"
    echo "  1. Read ${BROKEN%.docx}_validation_report.json"
    echo "  2. For each failure, apply str_replace edits to files in $UNPACK_DIR/"
    echo "     in priority order: F1 → F2 → F4 → F3"
    echo "     (F5/F6/F7 are Producer-side; hand back)"
    echo "  3. When done, run:"
    echo "       $0 repack '$UNPACK_DIR' '$BROKEN' '${BROKEN%.docx}_fixed.docx'"
    echo "  4. The repack step will auto-validate."
    echo ""
    echo "Cycle cap: 3 repair cycles total. After 3, escalate to Safe Template"
    echo "Rebuild per docs/04_FAILURE_PLAYBOOK.md §5."
    echo "================================================================"

    # Initialise a repair_log skeleton
    python3 - <<PYEOF > "$REPAIR_LOG"
import json, datetime
print(json.dumps({
    "version": "1.0",
    "cycle": 1,
    "started_at": datetime.datetime.utcnow().isoformat() + "Z",
    "input_file": "${BROKEN}",
    "unpacked_to": "${UNPACK_DIR}",
    "fixes_planned": "see ${BROKEN%.docx}_validation_report.json failures[]",
    "fixes_applied": [],
    "status": "awaiting_repairer_edits"
}, indent=2))
PYEOF
    echo "Repair log skeleton: $REPAIR_LOG"
    ;;

  *)
    echo "Usage: $0 {unpack|repack|cycle} ..."
    echo ""
    echo "  unpack <broken.docx>"
    echo "    → produces unpacked/ next to docx; Repairer applies str_replace edits"
    echo ""
    echo "  repack <unpacked/> <original.docx> <out.docx>"
    echo "    → repacks the edited XML, auto-runs validation"
    echo ""
    echo "  cycle <broken.docx>"
    echo "    → unpack + scaffold repair_log.json for one cycle"
    exit 2
    ;;
esac
