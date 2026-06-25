#!/usr/bin/env python3
"""读取macro-chart-specs-v2.json，用miningclaw-figure渲染SVG，注入HTML"""
import json, sys, os

sys.path.insert(0, os.path.expanduser("~/.claude/skills/miningclaw-figure"))
from figure_spec import FigureSpec, Encoding, RenderOpts
from render_product_svg import render_product_svg

def load_specs(path):
    with open(path) as f:
        return json.load(f)

def spec_to_figurespec(spec, idx):
    """将macro-chart-specs格式转换为FigureSpec"""
    chart_type = spec.get("chart_type", "horizontal-bar")
    data = spec.get("data", [])
    title = spec.get("title", "Chart")
    claim = spec.get("claim", spec.get("title", "Chart"))
    source_note = spec.get("source_note", "Data source unavailable")
    encoding_raw = spec.get("encoding", {})
    
    # 映射chart_type
    type_map = {
        "horizontal-bar": "horizontal-bar",
        "multi-series-line": "line",
        "signed-bar": "vertical-bar",
        "grouped-bar": "grouped-bar",
    }
    mc_type = type_map.get(chart_type, "horizontal-bar")
    
    # 构建Encoding：需全部6个必填字段
    xf = encoding_raw.get("x_field", "label")
    yf = encoding_raw.get("y_field", "value")
    lf = encoding_raw.get("label_field", xf)
    vf = encoding_raw.get("value_field", yf)
    xt = encoding_raw.get("x_title", "")
    yt = encoding_raw.get("y_title", "")
    unit = encoding_raw.get("unit", "value")
    
    encoding = Encoding(
        x_field=xf,
        y_field=yf,
        label_field=lf,
        value_field=vf,
        x_title=xt,
        y_title=yt,
        unit=unit,
    )
    
    # 构建FigureSpec
    fs = FigureSpec(
        claim=claim,
        chart_type=mc_type,
        data=data,
        encoding=encoding,
        title=title,
        source_note=source_note,
        opts=RenderOpts(
            theme="lynai",
            dimensions="report-wide",  # 1040px，适合A4报告
            output_format="html-embed" if mc_type == "horizontal-bar" else "svg",
            fig_id=f"fig-macro-{idx}",
        ),
    )
    return fs

def main():
    specs_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/macro-chart-specs-v2.json"
    html_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/macro-step2-report-wang-style.html"
    output_path = sys.argv[3] if len(sys.argv) > 3 else "/tmp/macro-report-figure-v1.1.html"

    specs = load_specs(specs_path)
    if isinstance(specs, dict):
        specs = specs.get("figure_specs", specs.get("charts", []))
    
    print(f"Loaded {len(specs)} chart specs")
    
    # 渲染每个图表
    charts = {}
    for i, spec in enumerate(specs):
        slug = spec.get("slug", f"chart-{i}")
        chart_type = spec.get("chart_type", "horizontal-bar")
        
        try:
            fs = spec_to_figurespec(spec, i)
            
            if chart_type == "horizontal-bar":
                svg_html = render_product_svg(fs)
                charts[slug] = svg_html
                print(f"  ✅ {slug} ({chart_type}) — rendered via render_product_svg")
            else:
                # 对其他类型，尝试render_figure（需要vl-convert）
                try:
                    from render_paper import render_figure
                    out = render_figure(fs)
                    charts[slug] = f'<img class="chart-img" src="data:image/svg+xml;base64,{__import__("base64").b64encode(out["svg"].encode()).decode()}" alt="{slug}"/>'
                    print(f"  ✅ {slug} ({chart_type}) — rendered via vega-lite")
                except (ImportError, RuntimeError) as e:
                    # fallback: 用简单的SVG
                    print(f"  ⚠️ {slug} ({chart_type}) — vl-convert not available: {e}, using fallback")
                    charts[slug] = _fallback_svg(spec, fs)
        except Exception as e:
            print(f"  ❌ {slug} — error: {e}")
            charts[slug] = f'<!-- CHART:{slug} RENDER ERROR: {e} -->'

    # 读取HTML并替换占位符
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    for slug, svg_html in charts.items():
        placeholder = f"<!-- CHART:{slug} -->"
        if placeholder in html:
            html = html.replace(placeholder, svg_html)
            print(f"  Injected: {slug}")
        else:
            # 尝试img标签占位符
            alt_placeholder = f'CHART:{slug}'
            if alt_placeholder in html:
                print(f"  ⚠️ {slug} — non-comment placeholder, trying img replacement")
                # 在其他占位符形式中替换
                html = html.replace(f'<!-- {alt_placeholder} -->', svg_html)
                html = html.replace(f'<img class="chart" src="data:image/png;base64,..." />', svg_html, 1)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\n✅ Output: {output_path} ({len(html)} chars, {len(charts)} charts injected)")

def _fallback_svg(spec, fs):
    """简单SVG fallback"""
    data = fs.data
    title = fs.title
    w, h = 800, 400
    bars = ""
    n = len(data)
    if n == 0:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><text x="400" y="200" text-anchor="middle" fill="#9ca3af">{title} (no data)</text></svg>'
    
    bar_w = (w - 100) / n - 10
    max_v = max(float(d.get(fs.encoding.y_field, 0)) for d in data) or 1
    
    xf = fs.encoding.label_field or getattr(fs.encoding, 'x_field', 'label')
    yf = fs.encoding.value_field or getattr(fs.encoding, 'y_field', 'value')
    for i, d in enumerate(data):
        label = str(d.get(xf, ""))
        val = float(d.get(yf, 0))
        bh = (val / max_v) * (h - 80)
        x = 60 + i * (bar_w + 10)
        y = h - 40 - bh
        color = "#14b8a6" if val >= 0 else "#ef4444"
        bars += f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bh}" fill="{color}" rx="2"/>'
        bars += f'<text x="{x+bar_w/2}" y="{h-15}" text-anchor="middle" font-size="10" fill="#6b7280">{label}</text>'
        bars += f'<text x="{x+bar_w/2}" y="{y-5}" text-anchor="middle" font-size="9" fill="#1f2937">{val}</text>'
    
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><text x="400" y="20" text-anchor="middle" font-size="14" fill="#1f2937" font-weight="600">{title}</text>{bars}</svg>'

if __name__ == "__main__":
    main()
