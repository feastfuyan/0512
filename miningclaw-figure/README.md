# miningclaw-figure v1.1.0

凌云智矿矿业作图 skill — 统一 FigureSpec 标准。  
图种由**数据和内容**决定；报告与论文不做区分，共享全部 16 种图类。

---

## 系统要求

| 项目 | 要求 |
|---|---|
| Python | 3.10 以上 |
| pydantic | ≥ 2.0（唯一硬依赖） |
| vl-convert-python | 可选，仅 `render_figure()` 输出 SVG/PDF/PNG 时需要 |
| pytest | 可选，仅跑测试时需要 |

---

## 安装

### 1. 复制 skill 目录

将整个 `miningclaw-figure/` 目录放到 `~/.claude/skills/` 下：

```bash
# macOS / Linux
cp -r miningclaw-figure ~/.claude/skills/

# Windows PowerShell
Copy-Item -Recurse miningclaw-figure $env:USERPROFILE\.claude\skills\
```

安装后目录结构：

```
~/.claude/skills/miningclaw-figure/
├── SKILL.md
├── figure_spec.py        ← 数据模型
├── figure_lint.py        ← lint 入口
├── render_paper.py       ← Vega-Lite 渲染（全图种）
├── render_product_svg.py ← HTML-embed 快速路径
├── parity.py             ← parity tripwire（团队维护者用）
├── requirements.txt
├── profiles/
├── vendored/
├── fonts/
└── tests/
```

### 2. 安装 Python 依赖

```bash
pip install pydantic>=2.0
```

如果需要 `render_figure()` 完整渲染（SVG / PDF / PNG）：

```bash
pip install vl-convert-python
```

> `render_product_svg()` 和 `lint_figure()` 是纯 Python，**不需要** vl-convert。

### 3. 验证安装

```bash
cd ~/.claude/skills/miningclaw-figure
python -m pytest tests/ -v
```

预期结果：**47 passed, 1 skipped**（skipped 是 vl-convert 未安装时的渲染测试，正常）。

---

## 快速上手

### 场景 A：LynAI 报告嵌入图（最常用）

horizontal-bar + HTML embed，纯 Python，无需 vl-convert。

```python
from figure_spec import FigureSpec, Encoding, RenderOpts
from render_product_svg import render_product_svg
from figure_lint import lint_product

fs = FigureSpec(
    claim="WA 前五矿权持有人占总持有量 62%。",
    chart_type="horizontal-bar",
    data=[
        {"label": "Rio Tinto",  "count": 148},
        {"label": "BHP",        "count": 121},
        {"label": "Fortescue",  "count":  89},
        {"label": "Hancock",    "count":  55},
        {"label": "Mineral Res","count":  41},
    ],
    encoding=Encoding(
        x_field="count", y_field="label",
        label_field="label", value_field="count",
        x_title="矿权数量", y_title="持有人",
        unit=" tenements",
    ),
    title="WA 铁矿矿权前五持有人",
    source_note="WA 矿权局 2026-06",
    opts=RenderOpts(
        output_format="html-embed",
        theme="lynai",          # 凌云 navy/teal 配色
        fig_id="fig-wa-01",
    ),
)

svg_html = render_product_svg(fs)   # 返回 <div class="chart-block" ...>...</div>
result = lint_product(svg_html)
print("通过" if result.passed else f"阻断: {result.blockers}")
```

---

### 场景 B：IC paper / 论文附图（Vega-Lite 渲染）

需要 `pip install vl-convert-python`。支持全部 16 种图类。

```python
from figure_spec import FigureSpec, Encoding, RenderOpts
from render_paper import render_figure
from figure_lint import lint_figure

fs = FigureSpec(
    claim="项目品位-吨位关系支持 1.0 g/t 截止品位以上的大吨位资源。",
    chart_type="grade-tonnage",          # 任意 16 种图类均可
    data=[
        {"cutoff": 0.5, "tonnes": 850, "grade": 1.45},
        {"cutoff": 0.8, "tonnes": 620, "grade": 1.72},
        {"cutoff": 1.0, "tonnes": 410, "grade": 2.05},
        {"cutoff": 1.5, "tonnes": 180, "grade": 2.68},
    ],
    encoding=Encoding(
        x_field="tonnes", y_field="grade",
        label_field="cutoff", value_field="tonnes",
        x_title="资源量 (Mt)", y_title="金品位 (g/t)",
        unit="g/t",
    ),
    title="品位-吨位曲线",
    source_note="QP 内审，2026-06",
    opts=RenderOpts(
        theme="nature",           # 色盲安全色板，期刊标准
        dimensions="183mm",       # "89mm" | "183mm" | "report-wide"
        output_format="svg",      # "svg" | "pdf" | "png"
        classification_category="indicated",
        is_economic_figure=False,
    ),
)

out = render_figure(fs)               # {"svg": str, "pdf": bytes|None, "png": bytes|None}
result = lint_figure(out["svg"], fs)  # G14 / I8 / claim / risk-palette 统一检查
if result.passed:
    with open("grade_tonnage.svg", "w", encoding="utf-8") as f:
        f.write(out["svg"])
else:
    print(f"阻断: {result.blockers}")
```

---

### 场景 C：NPV 瀑布图

```python
fs = FigureSpec(
    claim="基础情景 NPV₅ = 138 M USD，资本开支和运营成本是主要价值驱动项。",
    chart_type="waterfall",
    data=[
        {"label": "收入",      "value":  420},
        {"label": "运营成本",  "value": -180},
        {"label": "资本开支",  "value":  -72},
        {"label": "税费",      "value":  -30},
        {"label": "NPV₅",     "value":  138},
    ],
    encoding=Encoding(
        x_field="label", y_field="value",
        label_field="label", value_field="value",
        x_title="项目", y_title="USD M",
        unit="USD M",
    ),
    title="NPV 瀑布分解（基础情景）",
    source_note="Valuation model v3，2026-06",
    opts=RenderOpts(
        theme="lynai",
        dimensions="report-wide",   # 1040px，适合宽幅报告页
        waterfall_anchor="zero",
    ),
)
```

---

## 图种速查

| 数据类型 | 推荐图种 |
|---|---|
| 横向对比（多类别） | `horizontal-bar` |
| 纵向对比 | `vertical-bar`、`grouped-bar` |
| 时序 / 生产档案 | `line`、`area`、`production-profile` |
| 成本 / NPV 分解 | `waterfall` |
| 敏感性分析 | `tornado` |
| 资源分级堆积 | `resource-classification-stack` |
| 品位-吨位 | `grade-tonnage` |
| 全行业成本曲线 | `cost-curve` |
| 风险评估 | `risk-matrix`、`traffic-light-scorecard` |
| 散点 / 相关性 | `scatter` |

---

## RenderOpts 字段速查

| 字段 | 默认值 | 说明 |
|---|---|---|
| `theme` | `"nature"` | `"lynai"`（凌云 navy/teal）或 `"nature"`（色盲安全） |
| `dimensions` | `"183mm"` | `"89mm"` / `"183mm"` / `"report-wide"` |
| `output_format` | `"svg"` | `"svg"` / `"html-embed"` / `"pdf"` / `"png"` |
| `is_economic_figure` | `False` | True 时 G14 守门：Inferred 数据 → 阻断 |
| `classification_category` | `"n/a"` | `"inferred"` / `"indicated"` / `"measured"` / `"n/a"` 等 |
| `color_scale` | `"default"` | `"risk-semantic"` 启用红/橙/绿语义色板 |
| `fig_id` | `None` | html-embed 时注入 `id="fig-xxx"` |

---

## 关键守门规则

| 规则 | 触发条件 | 效果 |
|---|---|---|
| **G14** | `is_economic_figure=True` + `classification_category="inferred"` | `data_viz_integrity=0`，`passed=False` |
| **I8** | `encoding.unit` 为空或 SVG 轴标无单位 token | `labeling` 维度扣分，`passed=False` |
| **claim 非空** | `FigureSpec(claim="")` | Pydantic 验证失败，构建时即报错 |

---

## 环境变量

| 变量 | 用途 | 默认 |
|---|---|---|
| `MININGCLAWD_SRC` | parity 测试比对上游 `figure_checks.py`；仅 skill 维护者需要设置 | 王选策本机路径（fallback） |

普通使用者**不需要**设置任何环境变量。

---

## 常见问题

**Q: `render_figure` 报 `RuntimeError: vl-convert is not installed`**  
A: 运行 `pip install vl-convert-python`。如果只需要 `horizontal-bar` 的 HTML 嵌入，改用 `render_product_svg()` 即可，无需 vl-convert。

**Q: pytest 有 1 条 SKIPPED 是正常吗？**  
A: 是。`test_real_render_produces_svg` 在 vl-convert 未安装时自动 skip，属于预期行为。

**Q: parity 测试报 SKIPPED 而不是 PASSED**  
A: 正常。parity 测试需要 miningclawd 源码，设置 `MININGCLAWD_SRC` 环境变量后可恢复运行：  
```bash
# Windows
set MININGCLAWD_SRC=C:\path\to\lynai-miningclawd-monorepo\services\report\src
# macOS / Linux
export MININGCLAWD_SRC=/path/to/lynai-miningclawd-monorepo/services/report/src
```

**Q: `lint_figure` 返回 `passed=False`，blocker 是 G14**  
A: `opts.is_economic_figure=True` + `classification_category="inferred"` 同时成立。确认数据分类是否有误，或将 `is_economic_figure` 改为 `False`（若该图非经济性估值图）。

---

> 凌云智矿 Geovision AI Mines · miningclaw-figure v1.1.0 · 2026-06-25  
> ETCLOVG: C3 T3 G3 · GO
