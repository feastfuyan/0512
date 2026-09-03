---
name: black-gold-quotation
description: 生成黑金配色（黑色+金色高级感）的项目报价单 Word 文档。适用于「做报价单」「生成报价文档」「优化报价单排版」「项目报价」等场景，输出带黑金封面、功能清单表、模块报价汇总表、付款方式表的 .docx。当用户要求生成或美化商务报价单时可使用本技能。
agent_created: true
---

# Black Gold Quotation（黑金报价单生成器）

## 概述

用 Node.js `docx` 库生成黑金风格的项目报价单 .docx：纯黑封面 + 金色点缀、黑底金字表头、清晰灰色边框、页眉页脚。核心生成逻辑封装在 `scripts/build_quotation.js`，通过 JSON 配置驱动，无需每次重写代码。

## 标准模板（2026-08-27 定稿，用户指定）

**`assets/template_standard.docx`** 是用户确认的标准模板样张（3D 数字人实时互动系统报价单，v5 封面防溢出版）；**`assets/config_standard.json`** 是对应的完整标准配置。**任何新报价单都以这两份文件为基准**：

1. 复制 `assets/config_standard.json` 为临时配置，只改 `projectName` / `coverInfo` / `features` / `prices` / `payment` / `notes` 六项，版式、封面、间距一律不动
2. 生成后必须与标准模板做**特征核对**：输出文件应含 `P R O P O S A L`、`项 目 报 价 单`、封面节 `<w:vAlign w:val="both"/>`；缺任一特征说明脚本被改坏或生成失败，先修复再交付
3. 标准基线指标（模板定稿时的实测）：布局门禁 5 表全过、8 个 vMerge 延续格补齐、LibreOffice 真实渲染封面 1 页、三档行高系数（1.32/2.0/2.5）估算均 ≤15398 twips

改版式（封面、配色、表格结构）属于模板变更，需用户明确确认后同步更新这两份基准文件与本文档。

## 何时使用

- 用户要为某个项目生成正式报价单（Word 格式）
- 用户要美化/重排已有报价单（先读出内容 → 转成配置 → 重新生成）
- 用户指定「黑色配金色」「高级感」「奢华风」配色的商务文档

## 工作流程

### 1. 收集配置信息

以 `assets/config_standard.json`（标准模板配置）为底本，向用户确认或从已有文档/Excel 提取以下信息，组织成 JSON（字段结构如下）：

```json
{
  "projectName": "AI 皮肤检测及数字化平台",
  "coverInfo": {
    "客户名称": "同仁堂",
    "报价日期": "2026 年 8 月 10 日",
    "项目周期": "约 12 - 16 周"
  },
  "features": [
    { "name": "方案设计", "items": [
      { "name": "业务调研", "desc": "门店业务流程调研与需求梳理" }
    ]}
  ],
  "prices": [
    { "module": "方案设计", "amount": 20000 },
    { "module": "云服务（首年，按年计收）", "amount": 40000, "excludeTotal": true }
  ],
  "totalLabel": "项目总计（阶段一 + 阶段二）",
  "payment": [
    { "stage": "预付款", "percent": 60, "amount": 126000, "condition": "合同签订后 7 个工作日内" }
  ],
  "notes": ["本报价含税，有效期 30 天"]
}
```

**可选配置项**：
- `prices[].excludeTotal: true` — 该行在报价汇总表中列出但不计入合计（用于按年/按店计收的运营性费用）
- `totalLabel` — 自定义合计行文字（默认"合  计"），多阶段报价时写明总计口径

**生成前必须校验**：payment 的 percent 之和 = 100，amount 之和 = prices 中未标 excludeTotal 的总额；如有出入先向用户确认。

### 2. 确认环境

- Node 运行时：用 `node`（PATH 中任意 ≥18 版本均可；若本机有托管版本，用 `${WORKBUDDY_NODE:-node}`，默认指向 `~/.workbuddy/binaries/node/versions/22.22.2/bin/node` 的等价物，通过 `os.homedir()`/env 解析，不写死绝对路径）
- `docx` npm 包位置：通过环境变量 `DOCX_NODE_PATH` 指定（如 `~/.workbuddy/binaries/node/workspace/node_modules`），或在任意含 `node_modules/docx` 的工作目录直接运行
- 若包不存在：在一个可写工作目录执行 `npm install docx`，并把该目录经 `DOCX_NODE_PATH` 传入

### 3. 生成文档

```bash
# 1) 先把上面的 JSON 写入临时文件 quotation_config.json
NODE_PATH="${DOCX_NODE_PATH:-$HOME/.workbuddy/binaries/node/workspace/node_modules}" \
  ${WORKBUDDY_NODE:-node} \
  <skill目录>/scripts/build_quotation.js quotation_config.json "输出文件名.docx"
```

### 4. 生成后修复 + 验证（门禁，全部通过才能交付）

```bash
# ① 修复合并延续格（必须）：docx 库 rowSpan 生成的 vMerge continue 格缺 tcW/shd，
#    渲染时列宽错乱、底色断裂。此脚本从 restart 格复制 tcW/shd 到延续格（原子写入，安全）
python3 <skill目录>/scripts/fix_vmerge.py "输出文件名.docx"
# ② 布局门禁（必须 exit 0）：固定 dxa 列宽 / fixed 布局 / 无百分比宽度 / 每格有 tcW / 延续格与 restart 一致
python3 <skill目录>/scripts/check_layout.py "输出文件名.docx"
# ③ 结构校验
python3 <docx skill 路径>/scripts/office/validate.py "输出文件名.docx"
# ④ 金额抽查：汇总表金额、总计、付款比例
pandoc "输出文件名.docx" -t plain | grep -E "(¥|合|款)"
# ⑤ 功能清单文本抽查（防 items 字段写错导致表格空白）
pandoc "输出文件名.docx" -t plain | grep -E "(功能点|详细说明)"
```

`fix_vmerge.py` 与 `check_layout.py` 是防「转线上格式排版乱/表格缺失」的硬门禁（2026-08-27 巨子生物事件后加入），**任何一次生成都必须依次执行且退出码为 0**，不能跳过。校验通过后删除临时配置文件，用 present_files 展示结果。

## 设计规范（用户已确认，勿擅自更改）

| 元素 | 规格 |
|------|------|
| 封面 | **高级版 v5「黑金对撞·防溢出」**（2026-08-27 v4 两轮压缩后线上仍溢出，v5 改为结构性防溢出）：上下两分对撞构图——上部白底：左对齐金色字距排开 `P R O P O S A L` 眉头 + 金色竖条(140 twips 窄列底纹)夹持的特大号近黑标题「项 目 报 价 单」(42pt) + 金色项目名 + 灰色英文小字注 `QUOTATION & PROJECT PROPOSAL`；下部黑带：压顶金色细线(60 twips 表格行底纹) + 黑底信息区（金色标签/米白 #F5F2EA 值，上下 padding 150）+ 右下金色字距排开年份（自动从 coverInfo 日期提取）。**防溢出三板斧**：①封面节 `verticalAlign: VerticalAlignSection.BOTH`（支持的渲染器把内容分布到整页、黑带贴底；不支持的内容紧凑排页顶，均不溢出）；②**不放任何大留白 spacer**（确定性 gap 合计仅 3500 twips：300+800+2400，gap 值是绝对间距、渲染器无法膨胀）；③gap 段落一律加 `line: 20, lineRule: "exact"` 钳制行高，杜绝空段落行高膨胀。**不放任何公司联系信息/邮箱**。当前三档高度校验：1.32 系数 11218 / 2.0 系数 11990 / 2.5 系数 13085（页可用 15398）。禁止：空段落边框画线（线上丢弃）、整页满铺黑底（表格只能铺到页边距内，线上四边露白）、size 0 白色 SINGLE 边框（线上会显示成发丝线，一律用 BorderStyle.NONE） |
| 表头 | 黑底 (#1A1A1A) + 金色文字 (#C8A24B)，加粗 |
| 合计行 | 黑底 + 金色金额 |
| 数据行边框 | #AAAAAA（必须清晰可见；曾用 #EEEEEE 被用户反馈"看不见"，已废弃） |
| 表头/合计行边框 | #444444 |
| 斑马纹 | #FAFAFA |
| 表格布局 | **固定 dxa 列宽 + `tblLayout fixed`**（脚本内 `fixedTable()` 已内置，内容宽 9746 twips）。勿用百分比宽度——pct + 假 gridCol 转线上格式（腾讯文档/WPS）会排版错乱 |
| 章节标题 | 金色编号 + 深色标题 + 金色下划线 |
| 字体 | 微软雅黑全文统一 |
| 页眉 | 项目名 · 项目报价单（右对齐，浅灰小字 + 底部细线） |
| 页脚 | 居中页码「— N —」 |

## 常见迭代需求（历史经验）

- **改付款比例**：改 payment 配置的 percent/amount 即可，60/30/10 是当前默认
- **加/删模块**：同步改 features 和 prices 两个数组，保持模块名一致
- **预留 0 元接口**：prices 里加 `"amount": 0` 的行即可（如第三方 API 预留）
- **按模块打包报价，不报细项单价**：功能清单表只保留「功能模块/功能点/详细说明」三列，价格只出现在报价汇总表
- **总价控制**：调整各模块 amount 凑总价时，注意分配合理，勿出现 0.5 万这类零碎数

## 已知坑

- **生成后必须验证「输出文件本身」的特征，不能信「生成命令跑过了」**（2026-08-27 定稿标准模板时发现）：曾出现脚本已改（加了节 vAlign both）但桌面交付文件还是旧版的情况（含 vAlign、`<w:pgNumType/>` 等新特征全部缺失），而过程校验输出被误读为已生效。门禁除了布局检查，还要核对本次新加的特征标记（如 `w:vAlign w:val="both"`、封面眉头文字）确实出现在**最终输出文件**的 XML 里；同样，用户改价后重生成也需重验金额
- **docx 库的节垂直对齐用法**（docx 9.7.1）：节属性 `verticalAlign: VerticalAlignSection.BOTH`（值为 `"both"`）能正确输出 `<w:vAlign w:val="both"/>`，单节/多节均有效；注意别与单元格的 `VerticalAlign.CENTER` 混淆——单元格 vAlign 输出 `<w:vAlign w:val="center"/>`，校验时须限定在 sectPr 内检查，否则 55 处 cell vAlign 会造成误判「已写入」

- JS 脚本中 docx 构造器括号嵌套极深，手写易漏括号；改动 `build_quotation.js` 后先跑一次确认无语法错误
- 生成的 docx 在腾讯文档预览器中可能缓存旧版，用户看到旧内容时让其关闭重开文件
- `pandoc` 转 plain 时金额中的 `¥` 正常，若乱码用 `python-docx` 读取核对
- **百分比表格宽度会导致线上排版乱**（2026-08-27 巨子生物报价单发现）：docx 库 PERCENTAGE 类型写出 `w:type="pct" w:w="100%"` 且 gridCol 全为 100，转腾讯文档/WPS 线上格式时列宽计算错乱。已改为 `fixedTable()` 辅助函数（dxa + fixed 布局 + 真实 gridCol），新增表格一律走它；每次生成后跑 `scripts/check_layout.py` 门禁确认
- **合并单元格延续格（vMerge continue）缺 tcW/shd 会导致表格缺失**（2026-08-27 用户反馈"功能清单表格有缺失"）：docx 库 rowSpan 自动生成的延续格只有 `<w:vMerge w:val="continue"/>`，无 tcW 宽度无 shd 底色——渲染器列宽计算错乱、合并列底色一段灰一段白，视觉上像"表格缺失"。**必须**在生成后跑 `scripts/fix_vmerge.py`（从 restart 格复制 tcW/shd 到延续格，原子写入）；`check_layout.py` 门禁会强制校验延续格 tcW 与 restart 一致且带 shd。注意 fix_vmerge 内部须保留 tblPr/tblGrid，且先写临时文件再 os.replace（曾因原地 "w" 模式打开把源文件截断损坏）
- **配置 items 字段名必须是 `name` / `desc`**（不是 point/detail）：写错会导致功能清单表格全部空白而脚本不报错——生成后务必按第 4 步抽查功能清单文本
- **模块名字段名不统一会静默丢模块名**（2026-08-27 巨子生物发现）：脚本功能清单表读 `mod.name`、报价表读 `p.module`，配置若两处不一致会导致模块列空白/报价表模块名丢失且脚本不报错。脚本已兼容 `mod.name || mod.module`，但**生成后必须验证「功能清单表 + 报价汇总表」的模块名都出现**（用 zipfile 提取 w:t 文本核对，如 `商品推荐算法 -> 3`：功能清单 1 + 报价表 1 + 合计行场景）
- `amount` 支持传字符串（如 `"单独报价"`），`fmt()` 会原样显示且 `excludeTotal` 行不计入合计
- **封面线上兼容**（2026-08-27 用户反馈"封面的样式在在线情况下会出问题"）：①空段落 + 段落边框画的金色分隔线在线上渲染器会被丢弃（线消失）→ 改用金色细条表格行（底纹 + 段落 `line=80 lineRule=exact` 固定行高；注意此版 docx 库 TableRow 的 `height` 选项不输出 trHeight，行高靠段落固定行高钳制）；②整页满铺黑底在线上四边露白且高度不受控 → 改为带状黑金标题带；③`borders("FFFFFF", 0)` 的 size 0 SINGLE 边框线上可能渲染成发丝线 → 无边框一律用 `BorderStyle.NONE`（NO_BORDER 常量）
- **封面留白有单页高度预算，但估算永远追不上线上渲染器**（2026-08-27 v3/v4/v4-fix/v5 四次踩坑，教训）：A4 上下边距 720 时封面节可用 15398 twips。v3 用 1.15 系数低估溢出；v4 用 1.32 系数压线又溢出；v4-fix 用 1.5 系数留 2000 余量**线上仍然溢出**——腾讯文档线上渲染器对行高/空段落的膨胀无法用系数精确建模。**v5 最终解法是结构性防溢出（不再依赖估算）**：①封面节 `verticalAlign: VerticalAlignSection.BOTH`（docx 库原生支持，输出 `<w:vAlign w:val="both"/>`；支持者分布内容贴满页、不支持者紧凑排页顶，都不会溢出）；②**杜绝大留白 spacer**——spacer 的 before 值虽是绝对间距，但内容总高一旦压线，渲染器任何膨胀都会挤爆；改为「小 gap + vAlign」组合；③所有 gap 空段落加 `line: 20, lineRule: "exact"` 钳制（空段落自身行高再也不能膨胀）；④仍保留三档系数高度校验（1.32/2.0/2.5）作参考，要求 2.5 档也 ≤15398。估算方法：**先 `re.sub(r'<w:tbl>.*?</w:tbl>', '', cover)` 去掉表格再数顶层段落**（否则双重计数虚高近 5000 twips）；段落取 `max(400, 字号*10*系数)+before+after`，表格行取 `cell 上下 margin + 段落行高` 的最大值。改间距后必须用 LibreOffice `soffice --headless --convert-to pdf` 做真实渲染验证（单页 PDF）
- **本机文档渲染验证环境**（2026-08-27 搭建）：LibreOffice 已装（`brew install --cask libreoffice`，命令 `soffice`）；Pages 的 AppleScript 自动化被系统权限拦截（-10004）不可用。验证流程：①抽取封面单节做 docx（截取 document.xml 到第一个 sectPr 段落结尾，原子重写 zip）；②`soffice --headless --convert-to pdf`；③数 PDF 页数（`len(re.findall(rb'/Type\s*/Page[^s]', data))`）；④`sips -s format png` 转 PNG 后用 PIL 像素分析黑带位置（注意 PDF 转 PNG 带 alpha 通道，须先 `Image.alpha_composite` 合成白底再分析，否则透明区全黑）。venv 路径按 `${DOCX_PY:-python3}` 解析（本机 PIL 在 `~/.workbuddy/binaries/python/envs/default/bin/python`，用 `$HOME` 拼接，勿写死绝对路径）
- **check_layout 的窄列规则**（2026-08-27 v3 封面发现）：金色竖条这类刻意的装饰性窄列（80 twips gridCol）会被「gridCol ≤500 判假值」的老规则误拦。规则已细化为：≤500 的窄列只要与表内声明同宽的 dxa tcW 匹配（真实设计意图）即放行；百分比假网格（gridCol 100 + pct tcW）仍会被拦截。新表想用装饰窄列时，确保 `fixedTable()` 的列宽数组与每个 cell 的 tcW 一致即可通过门禁
