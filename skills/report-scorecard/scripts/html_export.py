#!/usr/bin/env python3
"""
html_export.py — HTML 可视化评分卡导出

职责：读取 score.py 输出的 JSON，生成自包含 HTML 评分卡。
依赖：无（纯标准库）
"""


import json
import sys
from pathlib import Path
from datetime import datetime
from html import escape as html_escape


def _score_bar_css(score, max_score=10) -> str:
    """生成分数条 CSS"""
    if score is None:
        return "background: #eee; width: 0%;"
    try:
        pct = min(float(score) / max_score * 100, 100)
    except (ValueError, TypeError):
        return "background: #eee; width: 0%;"

    if pct >= 80:
        color = "#4CAF50"
    elif pct >= 60:
        color = "#FF9800"
    else:
        color = "#F44336"

    return f"background: {color}; width: {pct}%;"


def _grade_color(grade: str) -> str:
    colors = {
        "A+": "#1B5E20", "A": "#2E7D32", "B+": "#F9A825",
        "B": "#FF8F00", "C": "#E65100", "F": "#B71C1C",
    }
    return colors.get(grade, "#333")


def _priority_badge(priority: str) -> str:
    colors = {"critical": "#F44336", "high": "#FF9800", "medium": "#FFC107"}
    bg = colors.get(priority, "#999")
    labels = {"critical": "🔴 严重", "high": "🟡 重要", "medium": "🟢 建议"}
    label = labels.get(priority, html_escape(priority))
    return f'<span style="background:{bg};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">{label}</span>'


def export_html(result_json_path: str, output_path: str = None) -> str:
    """
    导出 HTML 评分卡。

    Args:
        result_json_path: score.py 输出的 JSON 文件路径
        output_path: 输出路径

    Returns:
        输出文件路径
    """
    with open(result_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta = data["meta"]
    dimensions = data["dimensions"]
    ds = data.get("data_source_assessment", {})
    suggestions = data.get("optimization_suggestions", [])
    highlights = data.get("highlights", [])
    critical_issues = data.get("critical_issues", [])

    if output_path is None:
        base = Path(result_json_path).stem
        output_dir = Path(result_json_path).parent
        output_path = str(output_dir / f"{base}_评分卡.html")

    def _e(val):
        """HTML转义所有用户内容"""
        return html_escape(str(val)) if val else ""

    # 加载权重
    try:
        from score import load_config
        config = load_config(meta.get("template", "default"))
        weight_map = {d["id"]: d.get("weight", 1.0) for d in config["dimensions"]}
    except Exception:
        weight_map = {}

    # 构建 HTML
    dim_rows = ""
    for dim in dimensions:
        score = dim.get("score")
        try:
            s = float(score) if score is not None else None
        except (ValueError, TypeError):
            s = None

        weight = weight_map.get(dim.get("id", ""), 1.0)
        bar_css = _score_bar_css(s)
        score_display = f"{s:.1f}" if s is not None else "N/A"

        dim_rows += f"""
        <tr>
            <td class="dim-name">{_e(dim.get('name', dim.get('id', '')))}</td>
            <td class="dim-score"><span class="score-num">{score_display}</span>
                <div class="score-bar"><div class="score-fill" style="{bar_css}"></div></div>
            </td>
            <td>×{weight}</td>
            <td class="dim-eval">{_e(dim.get('evaluation', ''))}</td>
            <td class="dim-improve">{_e(dim.get('improvement', ''))}</td>
        </tr>"""

    sugg_rows = ""
    for s in suggestions:
        if not s:
            continue
        sugg_rows += f"""
        <tr>
            <td>{_priority_badge(s.get('priority', ''))}</td>
            <td><b>{_e(s.get('area', ''))}</b></td>
            <td>{_e(s.get('current_state', ''))}</td>
            <td>{_e(s.get('suggestion', ''))}</td>
            <td>{_e(s.get('impact', ''))}</td>
        </tr>"""

    highlight_items = "\n".join(f"<li>✅ {h}</li>" for h in highlights) if highlights else "<li>无</li>"
    issue_items = "\n".join(f"<li>⚠️ {i}</li>" for i in critical_issues) if critical_issues else "<li>无</li>"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>报告评分卡 — {_e(meta['report_name'])}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; color: #333; background: #f5f7fa; padding: 20px; }}
        .container {{ max-width: 900px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #003366, #1a5276); color: #fff; padding: 30px; }}
        .header h1 {{ font-size: 24px; margin-bottom: 8px; }}
        .header .meta {{ font-size: 13px; opacity: 0.8; }}
        .grade-display {{ display: flex; align-items: center; gap: 20px; margin-top: 20px; }}
        .grade-big {{ font-size: 48px; font-weight: 900; }}
        .score-big {{ font-size: 36px; font-weight: 700; }}
        .section {{ padding: 24px 30px; border-bottom: 1px solid #eee; }}
        .section h2 {{ font-size: 18px; color: #003366; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #003366; display: inline-block; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #f8f9fa; padding: 10px 12px; text-align: left; font-size: 13px; color: #666; border-bottom: 2px solid #dee2e6; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #eee; font-size: 13px; vertical-align: top; }}
        .dim-name {{ font-weight: 600; white-space: nowrap; }}
        .dim-score {{ min-width: 120px; }}
        .score-num {{ font-weight: 700; font-size: 16px; }}
        .score-bar {{ height: 6px; background: #eee; border-radius: 3px; margin-top: 4px; }}
        .score-fill {{ height: 100%; border-radius: 3px; transition: width 0.5s; }}
        .dim-eval {{ color: #555; }}
        .dim-improve {{ color: #e65100; }}
        .ds-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
        .ds-card {{ background: #f8f9fa; padding: 16px; border-radius: 8px; text-align: center; }}
        .ds-card .num {{ font-size: 28px; font-weight: 700; color: #003366; }}
        .ds-card .label {{ font-size: 12px; color: #888; margin-top: 4px; }}
        .highlight-list, .issue-list {{ list-style: none; padding: 0; }}
        .highlight-list li, .issue-list li {{ padding: 6px 0; font-size: 14px; }}
        @media print {{
            body {{ background: #fff; padding: 0; }}
            .container {{ box-shadow: none; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 报告评分卡</h1>
            <div class="meta">
                {_e(meta['report_name'])} · 模板: {meta.get('template', 'default')} ·
                模型: {meta.get('model', 'N/A')} · {meta.get('score_date', '')}
            </div>
            <div class="grade-display">
                <div>
                    <div class="grade-big" style="color:{_grade_color(meta['grade'])}">{meta['grade']}</div>
                    <div style="font-size:13px;opacity:0.8">{meta['grade_label']}</div>
                </div>
                <div>
                    <div class="score-big">{meta['total_score']}</div>
                    <div style="font-size:13px;opacity:0.8">/10</div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>维度评分</h2>
            <table>
                <thead>
                    <tr><th>维度</th><th>分数</th><th>权重</th><th>评价</th><th>改进建议</th></tr>
                </thead>
                <tbody>{dim_rows}</tbody>
            </table>
        </div>

        <div class="section">
            <h2>数据来源评估</h2>
            <div class="ds-grid">
                <div class="ds-card"><div class="num">{ds.get('sources_found', 0)}</div><div class="label">引用总数</div></div>
                <div class="ds-card"><div class="num">{ds.get('quality_score', 0)}</div><div class="label">质量分/10</div></div>
                <div class="ds-card"><div class="num">{ds.get('classified', {}).get('authoritative', 0)}</div><div class="label">权威来源</div></div>
            </div>
        </div>

        <div class="section">
            <h2>亮点与问题</h2>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
                <div>
                    <h3 style="font-size:14px;margin-bottom:8px;">🏆 亮点</h3>
                    <ul class="highlight-list">{highlight_items}</ul>
                </div>
                <div>
                    <h3 style="font-size:14px;margin-bottom:8px;">⚠️ 关键问题</h3>
                    <ul class="issue-list">{issue_items}</ul>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>优化建议</h2>
            <table>
                <thead><tr><th>优先级</th><th>领域</th><th>当前状态</th><th>改进方案</th><th>预期影响</th></tr></thead>
                <tbody>{sugg_rows}</tbody>
            </table>
        </div>
    </div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="导出 HTML 评分卡")
    parser.add_argument("json_file", help="评分结果 JSON 文件")
    parser.add_argument("--output", help="输出路径")
    args = parser.parse_args()

    path = export_html(args.json_file, args.output)
    print(f"✅ HTML 评分卡已保存: {path}")
