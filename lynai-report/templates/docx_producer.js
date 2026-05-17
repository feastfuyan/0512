/**
 * LynAI Report — DOCX Producer Template
 * =====================================
 *
 * Builds a publication-grade institutional research report (.docx) per the
 * GeoVision / LynAI Mines house style. Imports tokens from house_style.json.
 *
 * IMPORTANT — Before using this template, the agent operator MUST:
 *   1. Read /mnt/skills/public/docx/SKILL.md for the docx-js rules
 *   2. Run `npm install -g docx`
 *   3. Ensure house_style.json sits at ../templates/house_style.json
 *
 * Usage:
 *   node docx_producer.js \
 *     --content draft_v3.md \
 *     --charts charts/ \
 *     --tables tables.json \
 *     --meta report_meta.json \
 *     --out /mnt/user-data/outputs/<slug>.docx
 *
 * The content markdown is parsed by a thin parser in this file. For
 * production-grade markdown parsing, swap in `remark` or `marked` — the
 * built-in parser here handles the dialect produced by the Drafter agent
 * (deterministic ## §N — Title headings, [CHART::id], [TABLE::id]).
 */

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  Header, Footer, AlignmentType, PageOrientation, LevelFormat, HeadingLevel,
  BorderStyle, WidthType, ShadingType, VerticalAlign, PageNumber, PageBreak,
  TabStopType, TabStopPosition, TableOfContents, ExternalHyperlink,
  FootnoteReferenceRun,
} = require("docx");

// image-size pinned at v1.0.2 (see templates/runtime_paths.json npm_modules);
// 1.0.2 exports as a default function, so no dual-API shim is needed.
const sizeOf = require("image-size");
if (typeof sizeOf !== "function") {
  throw new Error("image-size@1.0.2 expected as a default function export. " +
                  "If a newer version is installed, pin to 1.0.2: npm install -g image-size@1.0.2");
}

// ============================================================================
// Load house style tokens (single source of truth)
// ============================================================================

const TOKENS_PATH = path.resolve(__dirname, "../templates/house_style.json");
if (!fs.existsSync(TOKENS_PATH)) {
  console.error(`FATAL: house style tokens not found at ${TOKENS_PATH}`);
  process.exit(2);
}
const TOK = JSON.parse(fs.readFileSync(TOKENS_PATH, "utf-8"));

const NAVY    = TOK.palette.primary_navy;     // "0D1F3C"
const GOLD    = TOK.palette.accent_gold;      // "C9A84C"
const TEXT    = TOK.palette.neutral_text;     // "1A1A1A"
const CAPTION = TOK.palette.neutral_caption;  // "555555"
const BG_ALT  = TOK.palette.neutral_bgalt;    // "FAFAFA"
const WHITE   = TOK.palette.white;            // "FFFFFF"

const SZ = TOK.size_half_pts;
const PAGE = TOK.page;
const SP = TOK.spacing_dxa;
const T = TOK.table;
const IMG = TOK.image_dims_emu;

// ============================================================================
// Helpers — common run/paragraph builders with house style baked in
// ============================================================================

const navyRun = (text, opts = {}) =>
  new TextRun({ text, font: "Georgia", color: NAVY, ...opts });

const bodyRun = (text, opts = {}) =>
  new TextRun({ text, font: "Georgia", size: SZ.body, color: TEXT, ...opts });

const captionRun = (text, opts = {}) =>
  new TextRun({
    text, font: "Georgia", size: SZ.caption, color: CAPTION,
    italics: true, ...opts,
  });

function bodyParagraph(text) {
  return new Paragraph({
    spacing: { before: SP.body_before, after: SP.body_after, line: SP.line_height },
    alignment: AlignmentType.JUSTIFIED,
    children: [bodyRun(text)],
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    pageBreakBefore: true,
    spacing: { before: SP.h1_before, after: SP.h1_after },
    children: [new TextRun({ text, font: "Georgia", bold: true, size: SZ.h1, color: NAVY })],
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: SP.h2_before, after: SP.h2_after },
    children: [new TextRun({ text, font: "Georgia", bold: true, size: SZ.h2, color: NAVY })],
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: SP.h3_before, after: SP.h3_after },
    children: [new TextRun({ text, font: "Georgia", bold: true, size: SZ.h3, color: NAVY })],
  });
}

function caption(text) {
  return new Paragraph({
    spacing: { before: 60, after: 240 },
    alignment: AlignmentType.LEFT,
    children: [captionRun(text)],
  });
}

function blankLine() {
  return new Paragraph({ children: [new TextRun("")] });
}

// ============================================================================
// Page furniture — header, footer (using tab stops, NEVER tables)
// ============================================================================

function buildHeader(meta) {
  return new Header({
    children: [
      new Paragraph({
        tabStops: [
          { type: TabStopType.RIGHT, position: TabStopPosition.MAX },
        ],
        border: {
          bottom: { style: BorderStyle.SINGLE, size: 6, color: NAVY, space: 4 },
        },
        children: [
          new TextRun({ text: meta.report_short_title, font: "Georgia",
                        size: SZ.caption, color: NAVY }),
          new TextRun({ text: "\t", font: "Georgia" }),
          new TextRun({ text: meta.date, font: "Georgia",
                        size: SZ.caption, color: NAVY }),
        ],
      }),
    ],
  });
}

function buildFooter() {
  return new Footer({
    children: [
      new Paragraph({
        tabStops: [
          { type: TabStopType.RIGHT, position: TabStopPosition.MAX },
        ],
        border: {
          top: { style: BorderStyle.SINGLE, size: 4, color: NAVY, space: 4 },
        },
        children: [
          new TextRun({ text: "GeoVision AI Mining | LynAI Mines",
                        font: "Georgia", size: SZ.footnote, color: CAPTION }),
          new TextRun({ text: "\tp. ", font: "Georgia",
                        size: SZ.footnote, color: CAPTION }),
          new TextRun({ children: [PageNumber.CURRENT],
                        font: "Georgia", size: SZ.footnote, color: CAPTION }),
          new TextRun({ text: " of ", font: "Georgia",
                        size: SZ.footnote, color: CAPTION }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES],
                        font: "Georgia", size: SZ.footnote, color: CAPTION }),
        ],
      }),
    ],
  });
}

// Empty header/footer for cover page
const blankHeader = new Header({ children: [new Paragraph({ children: [new TextRun("")] })] });
const blankFooter = new Footer({ children: [new Paragraph({ children: [new TextRun("")] })] });

// ============================================================================
// Cover page
// ============================================================================

function buildCover(meta) {
  return [
    // Generous top space
    blankLine(), blankLine(), blankLine(), blankLine(),
    blankLine(), blankLine(),

    // Gold rule
    new Paragraph({
      alignment: AlignmentType.LEFT,
      border: {
        bottom: { style: BorderStyle.SINGLE, size: 32, color: GOLD, space: 1 },
      },
      indent: { left: 0, right: 6000 },
      children: [new TextRun("")],
    }),

    blankLine(), blankLine(),

    // Wordmark
    new Paragraph({
      spacing: { after: 120 },
      children: [
        new TextRun({ text: TOK.cover.wordmark_text, font: "Georgia",
                      bold: true, size: 22, color: NAVY,
                      characterSpacing: 80 }),
      ],
    }),

    blankLine(),

    // Title
    new Paragraph({
      spacing: { after: 200 },
      children: [
        new TextRun({ text: meta.title, font: "Georgia",
                      bold: true, size: SZ.cover_title, color: NAVY }),
      ],
    }),

    // Subtitle
    meta.subtitle ? new Paragraph({
      spacing: { after: 400 },
      children: [
        new TextRun({ text: meta.subtitle, font: "Georgia",
                      size: SZ.cover_subtitle, color: NAVY }),
      ],
    }) : blankLine(),

    blankLine(),

    // Navy rule
    new Paragraph({
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: NAVY, space: 1 } },
      indent: { right: 8000 },
      children: [new TextRun("")],
    }),

    blankLine(),

    // Metadata block
    coverMetaLine("Date",   meta.date),
    coverMetaLine("Author", meta.author || "Xuan-Ce, PhD"),
    coverMetaLine("Ref",    meta.ref_id || `LYNAI-RR-${new Date().getFullYear()}-001`),

    // Bottom spacer
    ...Array(12).fill(0).map(() => blankLine()),

    // Legal block at the very bottom
    new Paragraph({
      children: [
        new TextRun({ text: TOK.cover.company_legal,
                      font: "Georgia", size: SZ.footnote, color: CAPTION }),
      ],
    }),
    new Paragraph({
      children: [
        new TextRun({ text: TOK.cover.confidential_note,
                      font: "Georgia", size: SZ.footnote,
                      color: CAPTION, italics: true }),
      ],
    }),

    new Paragraph({
      children: [new PageBreak()],
    }),
  ];
}

function coverMetaLine(label, value) {
  return new Paragraph({
    tabStops: [{ type: TabStopType.LEFT, position: 2000 }],
    spacing: { after: 80 },
    children: [
      new TextRun({ text: label, font: "Georgia",
                    size: SZ.cover_meta, color: CAPTION, bold: true }),
      new TextRun({ text: "\t", font: "Georgia" }),
      new TextRun({ text: value, font: "Georgia",
                    size: SZ.cover_meta, color: TEXT }),
    ],
  });
}

// ============================================================================
// Chart embed — computes EMU dimensions from the actual PNG aspect ratio
// ============================================================================

function buildChartEmbed(chartPath, captionText) {
  if (!fs.existsSync(chartPath)) {
    throw new Error(`Chart file not found: ${chartPath}`);
  }
  const buffer = fs.readFileSync(chartPath);
  const dims = sizeOf(buffer);

  // Target content width 6.54 inches at 96 dpi = 628 px
  // docx-js transformation expects pixels (it converts to EMU internally)
  const targetWidthPx = 628;
  const targetHeightPx = Math.round(targetWidthPx * dims.height / dims.width);

  const chartName = path.basename(chartPath, ".png");

  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 240, after: 60 },
      children: [
        new ImageRun({
          type: "png",
          data: buffer,
          transformation: {
            width: targetWidthPx,
            height: targetHeightPx,
          },
          altText: {
            title: chartName,
            description: captionText || chartName,
            name: chartName,
          },
        }),
      ],
    }),
    captionText ? caption(captionText) : null,
  ].filter(Boolean);
}

// ============================================================================
// Table builder — institutional grade
// ============================================================================

function buildTable(tableSpec) {
  const ncols = tableSpec.columns.length;
  const contentWidth = PAGE.width - PAGE.margin.left - PAGE.margin.right; // 9412
  const colWidth = Math.floor(contentWidth / ncols);
  const columnWidths = Array(ncols).fill(colWidth);
  // Adjust last column so sum equals contentWidth exactly
  columnWidths[ncols - 1] = contentWidth - colWidth * (ncols - 1);

  const navyBorder = { style: BorderStyle.SINGLE, size: T.border_size, color: T.border_color };
  const noBorder   = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };

  // Header row
  const headerCells = tableSpec.columns.map((col, i) =>
    new TableCell({
      width: { size: columnWidths[i], type: WidthType.DXA },
      shading: { fill: T.header_fill, type: ShadingType.CLEAR },
      margins: T.cell_margin,
      verticalAlign: VerticalAlign.CENTER,
      borders: {
        top:    navyBorder,
        bottom: navyBorder,
        left:   noBorder,
        right:  noBorder,
      },
      children: [
        new Paragraph({
          alignment: col.align === "right" ? AlignmentType.RIGHT
                     : col.align === "center" ? AlignmentType.CENTER
                     : AlignmentType.LEFT,
          children: [
            new TextRun({
              text: col.label, font: "Georgia",
              bold: true, size: SZ.table_header, color: WHITE,
            }),
          ],
        }),
      ],
    })
  );

  const headerRow = new TableRow({ tableHeader: true, children: headerCells });

  // Body rows
  const bodyRows = tableSpec.rows.map((row, rowIdx) => {
    const isAlt = rowIdx % 2 === 1;
    const fill = isAlt ? T.alt_row_shade : WHITE;
    const cells = row.map((cellValue, colIdx) => {
      const col = tableSpec.columns[colIdx];
      const align = col.align === "right" ? AlignmentType.RIGHT
                    : col.align === "center" ? AlignmentType.CENTER
                    : AlignmentType.LEFT;
      const negative = String(cellValue).startsWith("(") && String(cellValue).endsWith(")");
      return new TableCell({
        width: { size: columnWidths[colIdx], type: WidthType.DXA },
        shading: { fill, type: ShadingType.CLEAR },
        margins: T.cell_margin,
        verticalAlign: VerticalAlign.CENTER,
        borders: { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder },
        children: [
          new Paragraph({
            alignment: align,
            children: [
              new TextRun({
                text: String(cellValue), font: "Georgia",
                size: SZ.table_body,
                color: negative ? TOK.palette.alert_red : TEXT,
              }),
            ],
          }),
        ],
      });
    });
    return new TableRow({ children: cells });
  });

  // Final row gets a bottom border by setting cell border
  const lastRowCells = bodyRows[bodyRows.length - 1].options.children;
  lastRowCells.forEach(cell => {
    cell.options.borders.bottom = navyBorder;
  });

  const table = new Table({
    width: { size: contentWidth, type: WidthType.DXA },
    columnWidths,
    borders: {
      top: navyBorder,
      bottom: navyBorder,
      left: noBorder, right: noBorder,
      insideHorizontal: noBorder, insideVertical: noBorder,
    },
    rows: [headerRow, ...bodyRows],
  });

  return [
    new Paragraph({ spacing: { before: 200, after: 120 }, children: [new TextRun("")] }),
    table,
    tableSpec.caption ? caption(tableSpec.caption) : null,
    tableSpec.source_line ? caption(tableSpec.source_line) : null,
  ].filter(Boolean);
}

// ============================================================================
// Markdown parser (minimal — handles Drafter's deterministic dialect)
// ============================================================================

function parseMarkdown(md, chartsDir, tablesSpec) {
  const lines = md.split("\n");
  const elements = [];
  let buffer = [];

  const flushBuffer = () => {
    if (buffer.length > 0) {
      const text = buffer.join(" ").trim();
      if (text) elements.push(bodyParagraph(text));
      buffer = [];
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();

    // YAML front-matter is filtered by the caller — skip remaining "---" lines
    if (line === "---") continue;

    // H1 — section
    const h1Match = line.match(/^## §?\s*\d*\s*[—-]?\s*(.+)/);
    if (h1Match) {
      flushBuffer();
      elements.push(h1(h1Match[1].trim()));
      continue;
    }

    // H2
    if (line.startsWith("### ")) {
      flushBuffer();
      elements.push(h2(line.substring(4).trim()));
      continue;
    }

    // H3
    if (line.startsWith("#### ")) {
      flushBuffer();
      elements.push(h3(line.substring(5).trim()));
      continue;
    }

    // Chart placeholder
    const chartMatch = line.match(/^\[CHART::([^\]]+)\]$/);
    if (chartMatch) {
      flushBuffer();
      const chartId = chartMatch[1];
      const chartPath = path.join(chartsDir, `${chartId}.png`);
      // Next line may be the caption (italic)
      // Caller passes captions in via tablesSpec.chart_captions if needed; for
      // simplicity we omit auto-caption and rely on the placeholder convention.
      try {
        const elems = buildChartEmbed(chartPath, null);
        elements.push(...elems);
      } catch (e) {
        elements.push(bodyParagraph(`[CHART ERROR: ${chartId} — ${e.message}]`));
      }
      continue;
    }

    // Table placeholder
    const tableMatch = line.match(/^\[TABLE::([^\]]+)\]$/);
    if (tableMatch) {
      flushBuffer();
      const tableId = tableMatch[1];
      const tableSpec = tablesSpec.find(t => t.id === tableId);
      if (tableSpec) {
        elements.push(...buildTable(tableSpec));
      } else {
        elements.push(bodyParagraph(`[TABLE ERROR: ${tableId} not found in tables.json]`));
      }
      continue;
    }

    // Italic single-line (caption)
    if (line.startsWith("*") && line.endsWith("*") && line.length > 2) {
      flushBuffer();
      elements.push(caption(line.substring(1, line.length - 1)));
      continue;
    }

    // Empty line — paragraph break
    if (line === "") {
      flushBuffer();
      continue;
    }

    // Default: accumulate
    buffer.push(line);
  }
  flushBuffer();
  return elements;
}

// ============================================================================
// Top-level builder
// ============================================================================

function buildDocument({ contentPath, chartsDir, tablesPath, metaPath, outPath, shortfallNote = null }) {
  // Load all inputs
  const meta = JSON.parse(fs.readFileSync(metaPath, "utf-8"));
  const tablesSpec = fs.existsSync(tablesPath)
    ? JSON.parse(fs.readFileSync(tablesPath, "utf-8"))
    : [];
  let content = fs.readFileSync(contentPath, "utf-8");

  // Strip YAML front matter
  if (content.startsWith("---")) {
    const end = content.indexOf("\n---", 3);
    if (end > 0) content = content.substring(end + 4);
  }

  // v1.1: If gate_token.decision == DELIVER_WITH_SHORTFALL, prepend a banner
  // and the shortfall note before the body. Producer (build_docx.js) passes
  // the note explicitly; this template renders it as plain text + warning style.
  if (shortfallNote && typeof shortfallNote === "string" && shortfallNote.trim().length > 0) {
    const banner = "## §0 — DRAFT — DOES NOT MEET INSTITUTIONAL QUALITY GATE\n\n" +
                   "Cycle cap reached without convergence. See shortfall note below.\n\n" +
                   "**Shortfall note (per gate_token):**\n\n" +
                   shortfallNote.replace(/^/gm, "> ") + "\n\n---\n\n";
    content = banner + content;
  }

  // Parse body
  const bodyElements = parseMarkdown(content, chartsDir, tablesSpec);

  const doc = new Document({
    creator: meta.author || "LynAI Mines",
    title: meta.title,
    description: meta.subtitle || "",
    styles: {
      default: {
        document: { run: { font: "Georgia", size: SZ.body, color: TEXT } },
      },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal",
          quickFormat: true,
          run: { font: "Georgia", size: SZ.h1, bold: true, color: NAVY },
          paragraph: { spacing: { before: SP.h1_before, after: SP.h1_after },
                       outlineLevel: 0 } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal",
          quickFormat: true,
          run: { font: "Georgia", size: SZ.h2, bold: true, color: NAVY },
          paragraph: { spacing: { before: SP.h2_before, after: SP.h2_after },
                       outlineLevel: 1 } },
        { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal",
          quickFormat: true,
          run: { font: "Georgia", size: SZ.h3, bold: true, color: NAVY },
          paragraph: { spacing: { before: SP.h3_before, after: SP.h3_after },
                       outlineLevel: 2 } },
      ],
    },
    numbering: {
      config: [
        { reference: "bullets",
          levels: [{
            level: 0, format: LevelFormat.BULLET, text: "•",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } },
          }],
        },
        { reference: "numbers",
          levels: [{
            level: 0, format: LevelFormat.DECIMAL, text: "%1.",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } },
          }],
        },
      ],
    },
    sections: [
      // Section 1: Cover (no header/footer)
      {
        properties: {
          page: {
            size: { width: PAGE.width, height: PAGE.height },
            margin: PAGE.margin,
          },
          titlePage: true,
        },
        headers: { default: blankHeader, first: blankHeader },
        footers: { default: blankFooter, first: blankFooter },
        children: buildCover(meta),
      },
      // Section 2: Body
      {
        properties: {
          page: {
            size: { width: PAGE.width, height: PAGE.height },
            margin: PAGE.margin,
          },
        },
        headers: { default: buildHeader(meta) },
        footers: { default: buildFooter() },
        children: bodyElements,
      },
    ],
  });

  return Packer.toBuffer(doc).then(buffer => {
    fs.writeFileSync(outPath, buffer);
    console.log(`[ok] wrote ${outPath} (${buffer.length} bytes)`);
    return outPath;
  });
}

// ============================================================================
// CLI
// ============================================================================

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {};
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i].replace(/^--/, "");
    opts[key] = args[i + 1];
  }
  return opts;
}

if (require.main === module) {
  const opts = parseArgs();
  const required = ["content", "charts", "meta", "out"];
  for (const r of required) {
    if (!opts[r]) {
      console.error(`Missing required arg --${r}`);
      console.error("Usage: node docx_producer.js --content draft.md --charts charts/ --tables tables.json --meta meta.json --out out.docx");
      process.exit(1);
    }
  }
  buildDocument({
    contentPath: opts.content,
    chartsDir:   opts.charts,
    tablesPath:  opts.tables || "tables.json",
    metaPath:    opts.meta,
    outPath:     opts.out,
  }).catch(err => {
    console.error("[fatal]", err);
    process.exit(2);
  });
}

module.exports = { buildDocument };
