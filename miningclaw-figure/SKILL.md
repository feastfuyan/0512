---
name: miningclaw-figure
version: "1.1.0"
status: GO
description: >
  矿业作图技能 — 统一 FigureSpec 标准：图种由数据和内容决定，报告与论文不做区分。
  全部 16 种图类（horizontal-bar/grade-tonnage/waterfall/tornado/risk-matrix/cost-curve 等）
  统一经 Vega-Lite 渲染；theme/output_format/dimensions 控制外观，不限制图种。
  适用场景: mining figure, FigureSpec, 品位吨位/NPV瀑布/敏感性龙卷风/风险矩阵,
  publication figure, 报告图表, 矿业 IC 图, 43-101/JORC/VALMIN 附图,
  grade-tonnage, waterfall, tornado, risk-matrix, cost-curve.
when_to_invoke: >
  用户说 "画一张/做一张矿业图", "帮我出品位吨位曲线", "IC paper 需要 NPV 瀑布图",
  "报告需要风险矩阵", "publication-quality figure", "FigureSpec",
  "render_figure", "render_paper", "figure_lint", "lint_figure" 任意之一时触发。
  已有 FigureSpec 对象时也可直接调用 render_figure / lint_figure。
governance:
  constitution: "§2 因果先验"
  doctrine: "教典第 2 条 · 严苛评估"
  arxiv: ["T2-04:arXiv:2507.02825", "T2-05:arXiv:2406.12045"]
  enforced_gates: "G14 fail-closed(inferred+economic→REJECT); I8 单位 token 必须在 SVG 轴标; claim 非空断言; risk-palette 语义门"
input:
  fs: "FigureSpec — claim(str,非空) + chart_type(str,ALL_CHART_TYPES 16种) + data(list[dict]) + encoding(Encoding,unit必填) + opts(RenderOpts)"
output:
  render_figure: "dict{svg: str, pdf: bytes|None, png: bytes|None}"
  render_product_svg: "str — <div class='chart-block' id='fig-...'><svg ...></svg></div>"
  lint_figure: "LintResult{passed: bool, dim_scores: dict[str,float], blockers: list[str]}"
---

## 1. 一句话论点

**一张图 = 数据绑定的视觉论证。** `claim` 非空是强制不变量。
图种由**数据结构和内容论点**决定，与输出文档类型（报告 / 论文）无关。

---

## 2. 图种选择指南（数据驱动）

| 数据类型 | 推荐图种 |
|---|---|
| 对比（横向，多类别） | `horizontal-bar` |
| 对比（纵向，少类别） | `vertical-bar`、`grouped-bar` |
| 时序 / 生产档案 | `line`、`area`、`production-profile` |
| 累积分解（成本/NPV） | `waterfall` |
| 敏感性分析 | `tornado` |
| 资源分级堆积 | `resource-classification-stack` |
| 品位-吨位关系 | `grade-tonnage` |
| 全行业成本排列 | `cost-curve` |
| 风险评估 | `risk-matrix`、`traffic-light-scorecard` |
| 散点 / 相关性 | `scatter` |

---

## 3. 统一入口

```python
from figure_spec import FigureSpec, Encoding, RenderOpts
from render_paper import render_figure
from figure_lint import lint_figure

fs = FigureSpec(
    claim="…",                    # 必填，非空
    chart_type="grade-tonnage",   # 任意 16 种，由数据决定
    data=[…],
    encoding=Encoding(…, unit="g/t"),
    title="…",
    source_note="…",
    opts=RenderOpts(
        theme="lynai",            # "lynai" | "nature"（默认 nature）
        dimensions="report-wide", # "89mm" | "183mm" | "report-wide"
        output_format="svg",      # "svg" | "html-embed" | "pdf" | "png"
        # JORC / G14
        is_economic_figure=False,
        classification_category="n/a",
        # html-embed 时可设 fig_id
        fig_id=None,
    ),
)

out = render_figure(fs)           # {"svg": str, "pdf": bytes|None, "png": bytes|None}
result = lint_figure(out["svg"], fs)   # 统一 lint：G14 / I8 / risk-palette / claim
if result.passed:
    print("✓ 通过")
else:
    print(f"✗ 阻断: {result.blockers}")
```

### horizontal-bar HTML 嵌入（LynAI 报告快速路径）

```python
from render_product_svg import render_product_svg
from figure_lint import lint_product

fs = FigureSpec(
    claim="…",
    chart_type="horizontal-bar",
    …,
    opts=RenderOpts(output_format="html-embed", theme="lynai", fig_id="fig-mc06-3"),
)
svg_html = render_product_svg(fs)   # 确定性、字节稳定
result = lint_product(svg_html)     # 5 维确定性楼 ≥ 9.0
```

---

## 4. IO Schema

```
IN  (render_figure / render_product_svg):
  fs: FigureSpec {
    claim:        str  [非空，强制]
    chart_type:   str  [ALL_CHART_TYPES — 16 种全部可用]
    data:         list[dict]
    encoding:     Encoding { x_field, y_field, label_field, value_field,
                              x_title, y_title, unit (必填), ... }
    title:        str
    source_note:  str
    opts:         RenderOpts {
                    theme:                  "lynai" | "nature"
                    output_format:          "svg" | "html-embed" | "pdf" | "png"
                    dimensions:             "89mm" | "183mm" | "report-wide"
                    is_economic_figure:     bool
                    classification_category: "inferred" | "indicated" | "measured" | ...
                    color_scale:            "default" | "risk-semantic"
                    fig_id:                 str | None
                    ... (waterfall_anchor, tornado_base, diverging_domain, ...)
                  }
  }

OUT (render_figure):
  dict { svg: str, pdf: bytes|None, png: bytes|None }

OUT (render_product_svg):
  str  — <div class="chart-block" id="fig-..."><svg ...>...</svg></div>

OUT (lint_figure / lint_product):
  LintResult { passed: bool, dim_scores: dict[str,float], blockers: list[str] }
```

---

## 5. 组件文件速查

| 文件 | 职责 |
|---|---|
| `figure_spec.py` | FigureSpec + Encoding + **RenderOpts**（统一选项）+ validators |
| `render_paper.py` | **统一渲染器**：`render_figure()` 主入口 + Vega-Lite 全图种 + theme 注入；`render_paper` 为向后兼容别名 |
| `render_product_svg.py` | horizontal-bar HTML 嵌入快速路径（确定性、字节稳定，无 vl-convert 依赖） |
| `figure_lint.py` | `lint_figure()`（统一入口）+ `lint_product`（vendored 确定性楼）+ `lint_paper`（向后兼容） |
| `parity.py` + `parity_manifest.json` | 产品质量文件 hash-pin tripwire（C1/C2 可执行确认） |
| `profiles/lynai_report.py` | LynAI navy/teal 样式常量（`theme="lynai"` 时注入） |
| `profiles/nature_paper.py` | Nature 89/183mm 色盲安全 profile（`theme="nature"` 默认） |
| `vendored/figure_checks_vendored.py` | 产品 figure_checks 函数副本（gate-parity 锁） |
| `tests/golden_corpus/` | 产品 parity 黄金语料（honest_mc06/overflow/mc08_card/digit_leading） |

---

## 6. 诚实边界（Honest Boundary）

1. **`lint_figure` / `lint_product` 绿 ≠ 感知通过** — 确定性楼（5 维 ≥ 9.0）只是机器前置门；感知维须 Playwright + Opus vision judge 通过后方可发布。

2. **mc-08 diverging HTML-embed 今天门盲** — mc-08 的 diverging 图置于 `<div class="card">`，非注册 wrapper class，`extract_figures` 提取 0 张图。如需 html-embed 的 diverging，需先注册 wrapper class 并过绿提取测试。

3. **vl-convert 非纯 Python** — `render_figure` 构建期调用 Rust wheel + 内嵌 Deno-JS；非构建环境下 `vl_convert` 不可用会 `raise RuntimeError`（设计如此，非 bug）；字体须 vendored 至 `fonts/`。

4. **回收率现实性 → mineralogist** — `figure_lint` 检查单位 / Inferred-economic 违规，不认证数字本身的现实性，路由 `mineralogist`。

5. **真·艺术定制 → `nature-figure`** — 本 skill 默认 `nature_paper` profile；期刊级精细美工，路由 `nature-figure` skill 或人工。

---

## 7. ETCLOVG 治理锚（Triple Anchor）

```
宪法 §2/§C
  ∥ 套话 ≤15% · 语言锁定(中文解释/代码留英文) · 信息>简洁
  ∥ G14 fail-closed (inferred+economic → data_viz_integrity=0, REJECT)

教典严苛评估 (LYNAI-NATIVE-DOCTRINE G14 / G24 / G34)
  ∥ G14: Inferred 储量不入经济图 — lint_figure / lint_product 强制执行
  ∥ G24: 报告必须 thesis-clear — claim 非空对所有图强制 + lint 校验
  ∥ G34: CRITICAL 风险双签 — 触发路由至 compliance-luoyang + ceo-wangxc

arXiv + JORC/NI43-101/VALMIN 出版图标准
  ∥ JORC 2012 Table 1 / NI 43-101 §19 附图合规 — classification_note 必填于 resource/grade 图
  ∥ VALMIN 2015 §6.5 估值报告附图 — figure_lint 预证; QP/独立专家须 sign-off
  ∥ arXiv 矿业论文图标准 — nature_paper profile (89/183mm, 色盲安全色板, vendored 字体)
```

建后运行 `/etclovg-audit ~/.claude/skills/miningclaw-figure` 复验 GO。

---

## 8. 反模式与失败模式（Anti-patterns）

| 失败模式 | 症状 | 根因 | 对策 |
|---|---|---|---|
| **vl-convert 缺失** | `render_figure` 抛 `RuntimeError: vl_convert not installed` | 非构建环境，Rust wheel + Deno-JS 未装 | 构建期安装 `vl-convert-python`；或改用 `render_product_svg`（纯 Python，无需 vl-convert）|
| **G14 意外阻断** | `lint_figure` 返回 `passed=False`，blocker 含 `G14` | `opts.is_economic_figure=True` + `classification_category="inferred"` 同时成立 | 检查 `is_economic_figure` 是否误设为 True；或改用 `classification_category="indicated"` 若数据确为 indicated 级别 |
| **parity drift** | `test_parity_vendored_vs_product_identical` 失败 | 上游 `figure_checks.py` 变更但 `vendored/figure_checks_vendored.py` 未同步 | 每次上游更新后执行 `python parity.py --sync` 重新 pin hash；parity test 是早期预警，不要跳过 |
| **render_product_svg 忽略 dimensions** | 报告宽度没变化 | `render_product_svg` 走确定性路径，不读 `opts.dimensions`（固定 1040px HTML 逻辑） | 需要 Vega-Lite 宽度控制时改用 `render_figure`（须 vl-convert），不要混用两条路径 |
| **html-embed diverging 提取 0 张** | `extract_figures` 返回空列表 | `<div class="card">` 非注册 wrapper，`extract_figures` 只识别 `chart-block` | 参见诚实边界 §2；暂用 `output_format="svg"` 替代或注册 wrapper class |
| **claim 为空** | `lint_figure` blocker 含 `claim` | `FigureSpec(claim="")` 或 `claim=None` | `claim` 字段非空是强制不变量；每张图必须能用一句话陈述论点 |

---

> 凌云智矿 Geovision AI Mines · miningclaw-figure v1.1.0 · 2026-06-25
