// 黑金风格项目报价单生成器（配置驱动）
// 用法: NODE_PATH=<node_modules 路径> node build_quotation.js <config.json> <output.docx>
// config.json 结构见文末注释或 SKILL.md
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, AlignmentType, BorderStyle, VerticalAlign, Header, Footer,
  PageNumber, ShadingType, HeightRule, TableLayoutType, VerticalAlignSection,
} = require("docx");

const cfgPath = process.argv[2];
const outPath = process.argv[3] || "报价单.docx";
const cfg = JSON.parse(fs.readFileSync(cfgPath, "utf-8"));

// ─── 黑金配色（不要轻易改动，用户已确认） ───────────────────
const C_BLACK  = "1A1A1A"; // 封面底色 / 表头底色
const C_DARK   = "2D2D2D"; // 正文文字（比纯黑柔和）
const C_GOLD   = "C8A24B"; // 主金色
const C_GOLD_L = "E3C882"; // 亮金色（分隔线）
const C_MUTED  = "7A7A7A"; // 次要文字
const C_BORDER = "AAAAAA"; // 数据行边框（清晰可见，勿用 #EEEEEE）
const C_BORDER_D = "444444"; // 表头/合计行边框
const C_ROW_BG = "FAFAFA"; // 斑马纹行底色
const FONT = "Microsoft YaHei";

// 页面内容宽度（A4 11906 - 左右边距 1080*2），所有表格用固定 dxa 列宽 + fixed 布局，
// 百分比宽度 + 假 gridCol 在转线上格式（腾讯文档/WPS）时会排版错乱 —— 勿改回百分比
const CONTENT_W = 9746;
const DXA = (pct) => Math.round(CONTENT_W * pct / 100);
function fixedTable(columnWidths, rows, extra = {}) {
  return new Table({
    width: { size: columnWidths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    columnWidths,
    layout: TableLayoutType.FIXED,
    rows,
    ...extra,
  });
}

const fmt = (n) => typeof n === "string" ? n : "¥ " + Number(n).toLocaleString("en-US");

function txt(text, opts = {}) {
  return new TextRun({ text, font: FONT, size: opts.size || 21, color: opts.color || C_DARK, bold: opts.bold || false });
}

function cellPara(runs, align = AlignmentType.LEFT) {
  return new Paragraph({ alignment: align, spacing: { before: 40, after: 40 }, children: runs });
}

function cell(opts) {
  return new TableCell({
    width: opts.width ? { size: opts.width, type: WidthType.PERCENTAGE } : undefined,
    shading: opts.fill ? { type: ShadingType.CLEAR, fill: opts.fill } : undefined,
    verticalAlign: VerticalAlign.CENTER,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    columnSpan: opts.span,
    children: opts.children,
  });
}

function borders(color, size) {
  const b = { style: BorderStyle.SINGLE, size: size || 4, color };
  return { top: b, bottom: b, left: b, right: b };
}

// ─── 封面（高级版 v4「黑金对撞」）────────────────────────
// 设计语言（2026-08-27 三方向评审后用户选定 B）：
//   上部（白底）：左对齐金色字距眉头 PROPOSAL + 金色竖条夹持的特大标题 + 金色项目名
//                + 灰色英文小字注 QUOTATION & PROJECT PROPOSAL（编辑杂志感）
//   下部（黑带）：压顶金色细线 + 黑底信息区（金色标签 / 米白值）+ 右下金色字距年份
//   上下两分对撞构图，黑金品牌感最强；黑底只做页面下三分之一带状，不整页满铺
// 线上兼容约束（不可破坏）：
//  1) 一切线条均用「表格行底纹」实现，不用空段落边框画线（线上渲染器会丢弃）
//  2) 无边框一律 BorderStyle.NONE，不用 size 0 白色 SINGLE（线上会显示成发丝线）
//  3) 黑底只做带状，不整页满铺（表格只能铺到页边距内，线上四边露白）
const NO_BORDER = {
  top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
  bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
  left: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
  right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
};
const C_ONBLACK = "F5F2EA"; // 黑底上的米白文字（比纯白柔和）
function buildCover() {
  // 金色细条行（表格底纹实现，线上渲染可靠；h 为条高 twips）
  const goldBar = (h) => new TableRow({
    children: [new TableCell({
      width: { size: CONTENT_W, type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: C_GOLD },
      borders: NO_BORDER,
      margins: { top: 0, bottom: 0, left: 0, right: 0 },
      children: [new Paragraph({ spacing: { before: 0, after: 0, line: h, lineRule: "exact" }, children: [] })],
    })],
  });
  // gap 段落加行高钳制（line exact 20）：渲染器忽略 before 也只占 20 twips，杜绝空段落行高膨胀
  const gap = (before) => new Paragraph({ spacing: { before, after: 0, line: 20, lineRule: "exact" }, children: [] });

  // 底部黑带年份：从报价日期提取，找不到则取当前年
  const year = (() => {
    const s = Object.values(cfg.coverInfo || {}).join(" ");
    const m = s.match(/(?:19|20)\d{2}/);
    return m ? m[0] : String(new Date().getFullYear());
  })();

  // 标题块：左缘金色竖条（窄列底纹）+ 左对齐特大标题 + 金色项目名
  const TITLE_BAR_W = 140;
  const titleTable = fixedTable([TITLE_BAR_W, CONTENT_W - TITLE_BAR_W], [
    new TableRow({ children: [
      new TableCell({ // 金色竖条
        width: { size: TITLE_BAR_W, type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: C_GOLD },
        borders: NO_BORDER,
        margins: { top: 0, bottom: 0, left: 0, right: 0 },
        children: [new Paragraph({ spacing: { before: 0, after: 0 }, children: [] })],
      }),
      new TableCell({
        width: { size: CONTENT_W - TITLE_BAR_W, type: WidthType.DXA },
        borders: NO_BORDER,
        margins: { top: 260, bottom: 260, left: 500, right: 0 },
        children: [
          new Paragraph({ spacing: { before: 0, after: 0 }, children: [
            new TextRun({ text: "项 目 报 价 单", font: FONT, size: 84, color: C_BLACK, bold: true }),
          ] }),
          new Paragraph({ spacing: { before: 260, after: 0 }, children: [
            new TextRun({ text: cfg.projectName, font: FONT, size: 34, color: C_GOLD }),
          ] }),
        ],
      }),
    ] }),
  ]);

  // 底部黑带：压顶金线 + 金标签/米白值信息行 + 右下金色字距年份
  const BAND_LABEL_W = 2400;
  const blackCell = (w, children, margins) => new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: C_BLACK },
    borders: NO_BORDER,
    margins,
    children,
  });
  const bandRows = [
    goldBar(60),
    ...Object.entries(cfg.coverInfo || {}).map(([k, v]) => new TableRow({ children: [
      blackCell(BAND_LABEL_W, [cellPara([txt(k, { color: C_GOLD, size: 22 })])], { top: 150, bottom: 150, left: 500, right: 200 }),
      blackCell(CONTENT_W - BAND_LABEL_W, [cellPara([txt(String(v), { color: C_ONBLACK, size: 23 })])], { top: 150, bottom: 150, left: 0, right: 500 }),
    ] })),
    new TableRow({ children: [
      blackCell(BAND_LABEL_W, [new Paragraph({ spacing: { before: 0, after: 0 }, children: [] })], { top: 80, bottom: 80, left: 500, right: 200 }),
      blackCell(CONTENT_W - BAND_LABEL_W, [cellPara([
        new TextRun({ text: year.split("").join(" "), font: FONT, size: 26, color: C_GOLD, bold: true }),
      ], AlignmentType.RIGHT)], { top: 80, bottom: 280, left: 0, right: 500 }),
    ] }),
  ];

  return {
    properties: {
      page: { margin: { top: 720, right: 1080, bottom: 720, left: 1080 } },
      // 关键防溢出：节垂直两端对齐（vAlign both）。支持该属性的渲染器会把内容自动
      // 分布到整页（黑带被推到页底，视觉与原设计一致）；不支持的渲染器则内容紧凑
      // 排在页顶（也绝不溢出）。因此无需再放任何大留白 spacer。
      verticalAlign: VerticalAlignSection.BOTH,
    },
    children: [
      gap(300),
      // 眉头：金色字距排开的 PROPOSAL（左对齐）
      new Paragraph({ spacing: { before: 0, after: 100 }, children: [
        new TextRun({ text: "P R O P O S A L", font: FONT, size: 22, color: C_GOLD, bold: true }),
      ] }),
      gap(800),
      titleTable,
      // 英文小字注（编辑杂志感）
      new Paragraph({ spacing: { before: 300, after: 0 }, children: [
        new TextRun({ text: "Q U O T A T I O N   &   P R O J E C T   P R O P O S A L", font: FONT, size: 17, color: C_MUTED }),
      ] }),
      gap(2400),
      fixedTable([CONTENT_W], bandRows),
    ],
  };
}

// ─── 章节标题 ──────────────────────────────────────────
function sectionTitle(num, title) {
  return new Paragraph({
    spacing: { before: 480, after: 240 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: C_GOLD, space: 6 } },
    children: [
      new TextRun({ text: `${num}  `, font: FONT, size: 28, color: C_GOLD, bold: true }),
      new TextRun({ text: title, font: FONT, size: 28, color: C_DARK, bold: true }),
    ],
  });
}

// ─── 功能清单表 ────────────────────────────────────────
function buildFeatureTable() {
  const widths = [DXA(18), DXA(26), DXA(56)];
  const headCell = (t, i) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: C_BLACK },
    borders: borders(C_BORDER_D),
    verticalAlign: VerticalAlign.CENTER,
    margins: { top: 100, bottom: 100, left: 120, right: 120 },
    children: [cellPara([new TextRun({ text: t, font: FONT, size: 21, color: C_GOLD, bold: true })], AlignmentType.CENTER)],
  });
  const rows = [new TableRow({ height: { rule: HeightRule.ATLEAST, value: 480 }, tableHeader: true, children: ["功能模块", "功能点", "详细说明"].map(headCell) })];

  cfg.features.forEach((mod) => {
    mod.items.forEach((item, idx) => {
      const cells = [];
      if (idx === 0) {
        cells.push(new TableCell({
          width: { size: widths[0], type: WidthType.DXA },
          rowSpan: mod.items.length,
          shading: { type: ShadingType.CLEAR, fill: C_ROW_BG },
          borders: borders(C_BORDER),
          verticalAlign: VerticalAlign.CENTER,
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [cellPara([new TextRun({ text: mod.name || mod.module || "", font: FONT, size: 21, color: C_DARK, bold: true })], AlignmentType.CENTER)],
        }));
      }
      cells.push(new TableCell({ width: { size: widths[1], type: WidthType.DXA }, borders: borders(C_BORDER), margins: { top: 80, bottom: 80, left: 120, right: 120 }, verticalAlign: VerticalAlign.CENTER, children: [cellPara([txt(item.name, { bold: true })])] }));
      cells.push(new TableCell({ width: { size: widths[2], type: WidthType.DXA }, borders: borders(C_BORDER), margins: { top: 80, bottom: 80, left: 120, right: 120 }, verticalAlign: VerticalAlign.CENTER, children: [cellPara([txt(item.desc, { color: C_MUTED })])] }));
      rows.push(new TableRow({ children: cells }));
    });
  });
  return fixedTable(widths, rows);
}

// ─── 报价汇总表 ────────────────────────────────────────
function buildPriceTable() {
  const P_W = [DXA(60), DXA(40)];
  const mk = (t, opts = {}) => new TableCell({
    width: { size: opts.width || P_W[0], type: WidthType.DXA },
    shading: opts.fill ? { type: ShadingType.CLEAR, fill: opts.fill } : undefined,
    borders: borders(opts.borderColor || C_BORDER),
    verticalAlign: VerticalAlign.CENTER,
    margins: { top: 100, bottom: 100, left: 160, right: 160 },
    children: [cellPara([new TextRun({ text: t, font: FONT, size: opts.size || 22, color: opts.color || C_DARK, bold: opts.bold || false })], opts.align || AlignmentType.LEFT)],
  });
  const rows = [new TableRow({ height: { rule: HeightRule.ATLEAST, value: 500 }, tableHeader: true, children: [
    mk("报价模块", { fill: C_BLACK, color: C_GOLD, bold: true, borderColor: C_BORDER_D, align: AlignmentType.CENTER, width: P_W[0] }),
    mk("报价金额", { fill: C_BLACK, color: C_GOLD, bold: true, borderColor: C_BORDER_D, align: AlignmentType.CENTER, width: P_W[1] }),
  ]})];
  cfg.prices.forEach((p) => {
    rows.push(new TableRow({ children: [
      mk(p.module, { bold: true, width: P_W[0] }),
      mk(fmt(p.amount), { align: AlignmentType.RIGHT, width: P_W[1] }),
    ]}));
  });
  const total = cfg.prices.filter((p) => !p.excludeTotal).reduce((s, p) => s + (p.amount || 0), 0);
  rows.push(new TableRow({ children: [
    mk(cfg.totalLabel || "合  计", { fill: C_BLACK, color: C_GOLD, bold: true, borderColor: C_BORDER_D, align: AlignmentType.CENTER, width: P_W[0] }),
    mk(fmt(total), { fill: C_BLACK, color: C_GOLD, bold: true, borderColor: C_BORDER_D, align: AlignmentType.RIGHT, size: 24, width: P_W[1] }),
  ]}));
  return fixedTable(P_W, rows);
}

// ─── 付款方式表 ────────────────────────────────────────
function buildPaymentTable() {
  const PAY_W = [DXA(14), DXA(12), DXA(18), DXA(56)];
  const mk = (t, opts = {}) => new TableCell({
    width: { size: opts.width, type: WidthType.DXA },
    shading: opts.fill ? { type: ShadingType.CLEAR, fill: opts.fill } : undefined,
    borders: borders(opts.borderColor || C_BORDER),
    verticalAlign: VerticalAlign.CENTER,
    margins: { top: 100, bottom: 100, left: 120, right: 120 },
    children: [cellPara([new TextRun({ text: t, font: FONT, size: opts.size || 21, color: opts.color || C_DARK, bold: opts.bold || false })], opts.align || AlignmentType.CENTER)],
  });
  const rows = [new TableRow({ height: { rule: HeightRule.ATLEAST, value: 480 }, tableHeader: true, children: [
    ["阶段", 0], ["比例", 1], ["金额", 2], ["付款条件", 3]
  ].map(([t, i]) => mk(t, { fill: C_BLACK, color: C_GOLD, bold: true, borderColor: C_BORDER_D, width: PAY_W[i] })) })];
  cfg.payment.forEach((p) => {
    rows.push(new TableRow({ children: [
      mk(p.stage, { bold: true, width: PAY_W[0] }),
      mk(p.percent + "%", { width: PAY_W[1] }),
      mk(fmt(p.amount), { align: AlignmentType.RIGHT, width: PAY_W[2] }),
      mk(p.condition, { color: C_MUTED, align: AlignmentType.LEFT, width: PAY_W[3] }),
    ]}));
  });
  return fixedTable(PAY_W, rows);
}

// ─── 组装文档 ──────────────────────────────────────────
const doc = new Document({
  styles: { default: { document: { run: { font: FONT, size: 21, color: C_DARK } } } },
  sections: [
    buildCover(),
    {
      properties: { page: { margin: { top: 1200, right: 1080, bottom: 1200, left: 1080 } } },
      headers: {
        default: new Header({ children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: C_BORDER, space: 4 } },
          children: [
            txt(cfg.projectName + "  ·  项目报价单", { size: 16, color: C_MUTED }),
          ],
        })] }),
      },
      footers: {
        default: new Footer({ children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            txt("— ", { size: 16, color: C_MUTED }),
            new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: C_MUTED }),
            txt(" —", { size: 16, color: C_MUTED }),
          ],
        })] }),
      },
      children: [
        sectionTitle("01", "功能清单"),
        buildFeatureTable(),
        sectionTitle("02", "报价汇总"),
        buildPriceTable(),
        sectionTitle("03", "付款方式"),
        buildPaymentTable(),
        ...(cfg.notes || []).map((n) => new Paragraph({ spacing: { before: 120, after: 120 }, children: [txt("· " + n, { color: C_MUTED, size: 20 })] })),
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(outPath, buf);
  const total = cfg.prices.filter((p) => !p.excludeTotal).reduce((s, p) => s + (p.amount || 0), 0);
  console.log("OK ->", outPath, "| 总价:", fmt(total));
});

/*
config.json 示例:
{
  "projectName": "AI 皮肤检测及数字化平台",
  "coverInfo": { "客户名称": "同仁堂", "报价日期": "2026 年 8 月 10 日", "项目周期": "约 12 - 16 周" },
  "features": [
    { "name": "方案设计", "items": [ { "name": "业务调研", "desc": "..." } ] }
  ],
  "prices": [ { "module": "方案设计", "amount": 20000 } ],
  "payment": [ { "stage": "预付款", "percent": 60, "amount": 126000, "condition": "合同签订后 7 个工作日内" } ],
  "notes": ["报价含税，有效期 30 天"]
}
注意: payment 各项 percent 之和应为 100，amount 之和应等于 prices 总额，生成前自行校验。
*/
