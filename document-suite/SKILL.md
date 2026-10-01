---
name: document-suite
description: '办公文档处理全能套件，覆盖 Word(.docx/.doc)、Excel(.xlsx/.xlsm/.csv/.tsv)、PowerPoint(.pptx) 与 PDF 的创建、读取、编辑、解析、格式转换和批量处理。Triggers: 做一份Word文档, 生成word报告/合同/简历/模板, 读取docx内容, docx转pdf, 替换Word里的文字并保留格式, 做Excel表格, 写公式, 合并多个xlsx, xlsx转csv, 清洗凌乱的表格数据, 做个PPT/幻灯片/演示文稿, 读取pptx文字, 批量替换PPT模板内容, PDF提取文字/表格, PDF合并/拆分/旋转/加水印, 填PDF表单, 扫描件OCR识别, 简历批量提取信息到Excel, 按模板批量生成200份合同, markdown转Word带封面目录。任何以文档为最终交付物的任务都用本技能。'
agent_created: true
---

# Document Suite（办公文档处理套件）

## 概述

一个入口，四种格式的全能力。本技能把 Word / Excel / PPT / PDF 四类文档处理能力打包在一起，每个格式对应 `modules/` 下的一个模块：

| 格式 | 模块目录 | 能力速览 |
|------|---------|---------|
| Word | `modules/docx/` | 新建带样式的文档、解析/改写既有 docx、查找替换、修订与批注、doc↔docx |
| Excel | `modules/xlsx/` | 建表与公式、读改现有 workbook、数据透视与图表、格式与色彩规范、公式零错误 |
| PPT | `modules/pptx/` | 从零建 deck、按模板改稿、解析提取文字与结构、缩略图预览 |
| PDF | `modules/pdf/` | 文本/表格提取、合并拆分旋转水印、表单填写、扫描件 OCR、图片导出 |

## 第一步：路由

**先判断交付物是什么格式，再进对应模块。** 多格式混合的任务（如"Excel 数据 → Word 报告"）按环节依次进模块。

| 用户诉求 | 进入 | 先读 |
|---------|------|------|
| Word 报告 / 合同 / 简历 / 备忘录 / 模板 | docx | `modules/docx/GUIDE.md` |
| 读取、提取、改写 .docx 内容 / 保留格式做替换 | docx | `modules/docx/GUIDE.md` |
| 表格 / 报表 / 台账 / 财务模型 / 公式 | xlsx | `modules/xlsx/GUIDE.md` |
| 清洗乱数据、合并多份表格、csv↔xlsx | xlsx | `modules/xlsx/GUIDE.md` |
| PPT / 幻灯片 / 汇报稿 / pitch deck | pptx | `modules/pptx/GUIDE.md` |
| 按现有 PPT 模板改内容 | pptx | `modules/pptx/editing.md` |
| PDF 合并拆分 / 提取 / 表单 / OCR | pdf | `modules/pdf/GUIDE.md` |

**跨格式转换**：以「产出物」为准选模块 —— docx→pdf 进 docx（模块内自带转 PDF 能力），xlsx→csv 进 xlsx，pptx→pdf 进 pptx，图片→pdf 进 pdf。

## 第二步：进模块

进入模块后，**先完整读一遍该模块的 `GUIDE.md`**，它是该格式的操作手册（含可直接复制的命令与代码片段）。模块内还有专题文档：

- `modules/pptx/editing.md` —— 基于模板编辑/新建演示稿
- `modules/pptx/pptxgenjs.md` —— 从零用 pptxgenjs 建 deck
- `modules/pdf/forms.md` —— PDF 表单识别与填写
- `modules/pdf/reference.md` —— PDF 进阶用法与 JS 库

**模块内所有 `scripts/...` 路径都是相对于该模块目录的**。例如 docx 模块里的 `python scripts/office/unpack.py`，实际执行时要在 `modules/docx/` 下运行，或把路径补全为 `modules/docx/scripts/office/unpack.py`。

## 通用铁律

这几条适用于全部四种格式，优先级高于模块自己的建议：

1. **先问用途再动手**：文档给谁看、什么场合，直接决定风格（正式/简洁/汇报/存档）。用途不明就先确认。
2. **不覆盖原始文件**：修改既有文档前先备份，默认输出到新文件（如 `原名_已修改.docx`）。原模板、原始数据一律保留。
3. **尊重既有格式**：编辑已有文档时严格沿用原样式、字体、配色、约定，**不擅自"标准化"**。既有模板规范永远优先于本技能里的默认建议。
4. **批量任务脚本化**：处理几十上百份文档时写脚本跑，不手工点。批量生成（邮件合并式）从 Excel/CSV 读数据，产出用「模板名_序号」有序命名。
5. **中文排版规范**：中文文档用中文字体（宋体/黑体/微软雅黑）、中英文之间加空格、标点全角、段首缩进 2 字符、行距 1.5 倍。
6. **编码要对**：写给 Excel 的 CSV 一律用 `utf-8-sig`（带 BOM），否则中文会乱码；遇到乱码先查编码根因，不要靠猜。
7. **超长文档分块**：>50 页的文档分章节处理，方便用户逐段 review。
8. **交付即验**：生成后做一次自检——打开确认能正常渲染、公式无报错、页数符合预期、关键特征（封面/目录/表头）存在。发现异常先修复再交付。

## 环境依赖

按用到的模块装，不必一次全装。

**Python**（docx / xlsx / pptx / pdf 的脚本都依赖）

```bash
pip install pypdf pdfplumber reportlab openpyxl python-docx python-pptx Pillow
# PDF 表单填写额外需要
pip install pdf-lib pypdfium2
# 扫描件 OCR（还需系统级 tesseract）
pip install pytesseract
brew install tesseract tesseract-lang
# PPT 内容提取
pip install "markitdown[pptx]"
```

**Node.js**（从零生成 docx / pptx 时用）

```bash
npm install -g docx pptxgenjs
```

**LibreOffice**（格式转换与渲染预览，强烈建议装）

```bash
brew install --cask libreoffice
```

模块脚本里常见的外部命令：`pandoc`（文本转换）、`pdftoppm`（PDF 转图，属 poppler）、`markitdown`（文档转 markdown）。缺失时脚本会报错，按提示补装。

## 边界与原则

- **OCR 不保证 100%**：扫描件识别准确率通常 90%–95%，输出后必须提示用户复核关键字段（金额、身份证号、日期）。
- **文件体积意识**：产出超过 100MB 时主动提示，建议拆分或压缩。
- **合同等法律效力文档**：可以做排版与要素替换，但要提示用户最终由专业人员审核，不替代法律意见。
- **不做无关任务**：不处理 Google Docs 在线编辑、不写与文档无关的通用代码。

## 模块目录结构

```
document-suite/
├── SKILL.md              ← 本文件（总入口，先读这里）
├── references/
│   └── packaging-notes.md ← 打包来源与许可说明
└── modules/
    ├── docx/             ← GUIDE.md + scripts/（office 工具链、schema、模板）
    ├── xlsx/             ← GUIDE.md + scripts/（recalc、office 工具链）
    ├── pptx/             ← GUIDE.md + editing.md + pptxgenjs.md + scripts/
    └── pdf/              ← GUIDE.md + forms.md + reference.md + scripts/
```