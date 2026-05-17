#!/usr/bin/env bash
# validate_docx.sh — LynAI 4-check DOCX+PDF validation harness (v1.2)
#
# Runs the four Validator checks per docs/04_FAILURE_PLAYBOOK.md §1:
#   1. Schema validation     (validate.py from docx skill)
#   2. PDF render (D-11)      (soffice.py --convert-to pdf into LYNAI_OUTPUTS_DIR — this IS the delivered PDF)
#   3. Asset integrity        (check_assets.py — Python zipfile, cross-platform)
#   4. PDF integrity          (check_pdf.py — header / trailer / page count / parity)
#
# v1.2 change: the PDF is no longer a disposable validator side-effect; it is
# the second of two deliverables. Check 2 places it directly in LYNAI_OUTPUTS_DIR.
#
# Emits validation_report.json next to the .docx (or to --report path).
# Exit codes:
#   0 = all checks passed
#   1 = one or more checks failed
#   2 = harness error (missing tool, bad args)
#
# Usage:
#   ./validate_docx.sh <path/to/file.docx> [--report <path/to/validation_report.json>]

set -u
set -o pipefail

# ---------- args ----------

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <path/to/file.docx> [--report <report.json>]" >&2
  exit 2
fi

DOCX_PATH="$1"
shift
REPORT_PATH=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --report) REPORT_PATH="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ ! -f "$DOCX_PATH" ]]; then
  echo "FATAL: file not found: $DOCX_PATH" >&2
  exit 2
fi

# Default report location
if [[ -z "$REPORT_PATH" ]]; then
  REPORT_PATH="${DOCX_PATH%.docx}_validation_report.json"
fi

# ---------- toolkit locations (env-driven; falls back to harness defaults) ----------

: "${DOCX_SKILL_ROOT:=/mnt/skills/public/docx}"
: "${LYNAI_OUTPUTS_DIR:=/mnt/user-data/outputs}"
DOCX_SKILL_SCRIPTS="${DOCX_SKILL_ROOT}/scripts/office"
VALIDATE_PY="${DOCX_SKILL_SCRIPTS}/validate.py"
SOFFICE_PY="${DOCX_SKILL_SCRIPTS}/soffice.py"
CHECK_ASSETS_PY="$(dirname "$0")/check_assets.py"
CHECK_PDF_PY="$(dirname "$0")/check_pdf.py"

for tool in "$VALIDATE_PY" "$SOFFICE_PY"; do
  if [[ ! -f "$tool" ]]; then
    echo "FATAL: required docx skill tool missing: $tool" >&2
    exit 2
  fi
done

# Ensure outputs dir exists; the PDF is rendered DIRECTLY into it (not a tmp dir)
mkdir -p "$LYNAI_OUTPUTS_DIR" 2>/dev/null || true

# ---------- check 1: schema ----------

echo "[1/3] Schema validation..."
SCHEMA_OUT="$(python3 "$VALIDATE_PY" "$DOCX_PATH" 2>&1)"
SCHEMA_RC=$?
if [[ $SCHEMA_RC -eq 0 ]]; then
  SCHEMA_PASS="true"
  SCHEMA_MESSAGES="[]"
  echo "      pass"
else
  SCHEMA_PASS="false"
  SCHEMA_MESSAGES="$(printf '%s' "$SCHEMA_OUT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().splitlines()))')"
  echo "      FAIL"
fi

# ---------- check 2: PDF render (D-11 — this PDF is the DELIVERED pdf) ----------

echo "[2/4] PDF render to LYNAI_OUTPUTS_DIR (delivered, not temporary)..."
RENDER_PASS="false"
PDF_SIZE_KB=0
PAGES=0

if python3 "$SOFFICE_PY" --headless --convert-to pdf --outdir "$LYNAI_OUTPUTS_DIR" "$DOCX_PATH" > /dev/null 2>&1; then
  BASE="$(basename "$DOCX_PATH" .docx)"
  PDF_FILE="${TMP_VALIDATE}/${BASE}.pdf"
  if [[ -f "$PDF_FILE" ]]; then
    BYTES=$(stat -c%s "$PDF_FILE" 2>/dev/null || stat -f%z "$PDF_FILE")
    PDF_SIZE_KB=$((BYTES / 1024))
    # Try to count pages via pdfinfo if available, else from PDF structure
    if command -v pdfinfo >/dev/null 2>&1; then
      PAGES=$(pdfinfo "$PDF_FILE" 2>/dev/null | awk '/^Pages:/ {print $2}')
      [[ -z "$PAGES" ]] && PAGES=0
    else
      PAGES=$(grep -ac '^/Type[[:space:]]*/Page[^s]' "$PDF_FILE" 2>/dev/null || echo 0)
    fi
    if [[ $PDF_SIZE_KB -ge 5 && $PAGES -ge 2 ]]; then
      RENDER_PASS="true"
      echo "      pass (${PDF_SIZE_KB} KB, ${PAGES} pages)"
    else
      echo "      FAIL (${PDF_SIZE_KB} KB, ${PAGES} pages — needs ≥5 KB, ≥2 pages)"
    fi
  else
    echo "      FAIL — no PDF produced"
  fi
else
  echo "      FAIL — soffice exited non-zero"
fi

# ---------- check 3: asset integrity (Python zipfile, cross-platform) ----------

echo "[3/4] Asset integrity (Python zipfile)..."
ASSET_PASS="true"
IMAGE_COUNT=0
BAD_ASSETS_JSON="[]"

if [[ ! -f "$CHECK_ASSETS_PY" ]]; then
  echo "      FATAL: check_assets.py missing at $CHECK_ASSETS_PY" >&2
  exit 2
fi

ASSET_OUT="$(python3 "$CHECK_ASSETS_PY" "$DOCX_PATH" 2>&1)"
ASSET_RC=$?
if [[ $ASSET_RC -eq 0 ]]; then
  IMAGE_COUNT=$(echo "$ASSET_OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("image_count", 0))')
  echo "      pass (${IMAGE_COUNT} images)"
else
  ASSET_PASS="false"
  IMAGE_COUNT=$(echo "$ASSET_OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("image_count", 0))' 2>/dev/null || echo 0)
  BAD_ASSETS_JSON=$(echo "$ASSET_OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps(d.get("bad_assets", [])))' 2>/dev/null || echo "[]")
  echo "      FAIL — see report"
fi
# Legacy variable for compatibility with the heredoc below
BAD_ASSETS=()

# ---------- check 4: PDF integrity (v1.2 — deliverable, not temp) ----------

echo "[4/4] PDF integrity (check_pdf.py)..."
PDF_INTEGRITY_PASS="false"
PDF_PAGES=0

if [[ ! -f "$CHECK_PDF_PY" ]]; then
  echo "      FATAL: check_pdf.py missing at $CHECK_PDF_PY" >&2
  exit 2
fi

if [[ -f "$DELIVERED_PDF" ]]; then
  PDF_OUT="$(python3 "$CHECK_PDF_PY" "$DELIVERED_PDF" --min-pages 2 2>&1)"
  PDF_RC=$?
  if [[ $PDF_RC -eq 0 ]]; then
    PDF_INTEGRITY_PASS="true"
    PDF_PAGES=$(echo "$PDF_OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("pages", 0))' 2>/dev/null || echo 0)
    echo "      pass (${PDF_PAGES} pages, deliverable at ${DELIVERED_PDF})"
  else
    echo "      FAIL — see report"
  fi
else
  echo "      FAIL — delivered PDF missing at ${DELIVERED_PDF}"
fi

# ---------- aggregate verdict (v1.2 — 4 checks) ----------

if [[ "$SCHEMA_PASS" == "true" && "$RENDER_PASS" == "true" && "$ASSET_PASS" == "true" && "$PDF_INTEGRITY_PASS" == "true" ]]; then
  OVERALL="true"
else
  OVERALL="false"
fi

# ---------- write JSON report ----------

python3 - <<PYEOF > "$REPORT_PATH"
import json, datetime
overall              = json.loads("${OVERALL}")
schema_pass          = json.loads("${SCHEMA_PASS}")
render_pass          = json.loads("${RENDER_PASS}")
asset_pass           = json.loads("${ASSET_PASS}")
pdf_integrity_pass   = json.loads("${PDF_INTEGRITY_PASS}")
report = {
    "version": "1.2",
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    "file": "${DOCX_PATH}",
    "pdf_file": "${DELIVERED_PDF}",
    "checks": {
        "schema":          {"pass": schema_pass, "messages": ${SCHEMA_MESSAGES}},
        "open_render":     {"pass": render_pass, "pdf_size_kb": ${PDF_SIZE_KB}, "pages": ${PAGES}, "delivered_pdf_path": "${DELIVERED_PDF}"},
        "asset_integrity": {"pass": asset_pass, "image_count": ${IMAGE_COUNT}, "bad_assets": ${BAD_ASSETS_JSON}},
        "pdf_integrity":   {"pass": pdf_integrity_pass, "pages": ${PDF_PAGES}}
    },
    "overall_pass": overall,
    "failures": []
}
print(json.dumps(report, indent=2))
PYEOF

echo ""
echo "Report written to: $REPORT_PATH"
echo "Overall: $OVERALL"

if [[ "$OVERALL" == "true" ]]; then
  exit 0
else
  exit 1
fi
