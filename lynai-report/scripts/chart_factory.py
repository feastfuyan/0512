#!/usr/bin/env python3
"""
chart_factory.py — Chart dispatcher with paper-skill integration (v1.3, D-13)
==============================================================================

Routes each chart_spec to the appropriate rendering backend:

  * Financial/structural charts (line, bar, barh, scatter, area, stacked_bar,
    waterfall, histogram, dual_axis) → lynai-report's own render_chart.py
    (GS / Top of Mind house style, defined in docs/03_HOUSE_STYLE_GUIDE.md §5).

  * Geochemistry charts (ree_pattern, spider, heatmap, dendrogram, boxplot,
    correlation_heatmap) → paper skill's visualizer agent at
    ~/.claude/skills/paper/agents/visualizer.py.

The dispatcher exists so a mining-research report can mix financial
visualizations with geochem plots in the same document without Chart-Smith
having to know how to render both.

Usage:
    python chart_factory.py --spec chart_specs.json --out charts/

Spec extension (D-13):
    Each chart spec may carry an optional 'backend' field:
        'lynai'  — force lynai/render_chart.py
        'paper'  — force paper/visualizer
        'auto'   — route based on type (default)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent

LYNAI_TYPES = {
    "line", "bar", "barh", "scatter", "area",
    "stacked_bar", "waterfall", "histogram", "dual_axis",
}
PAPER_TYPES = {
    "ree_pattern", "spider", "spider_diagram", "heatmap",
    "correlation_heatmap", "dendrogram", "cluster_dendrogram", "boxplot",
}


CHART_ID_RE = __import__("re").compile(r"^chart_[a-z0-9_]{1,60}$")


def _validate_id(spec: dict) -> bool:
    """v1.4.2 D-16 P1-5: chart id sandbox — defeats path traversal in spec.id."""
    return bool(CHART_ID_RE.match(spec.get("id", "")))


def _route(chart_type: str, backend_hint: str) -> str:
    if backend_hint in ("lynai", "paper"):
        return backend_hint
    if chart_type in PAPER_TYPES:
        return "paper"
    return "lynai"


def _paper_visualizer_available() -> Path | None:
    """Locate the paper skill's visualizer module."""
    candidate = Path.home() / ".claude" / "skills" / "paper" / "agents" / "visualizer.py"
    return candidate if candidate.exists() else None


def _render_paper_chart(spec: dict, out_dir: Path) -> str | None:
    """Invoke paper.VisualizerAgent for geochem charts."""
    viz_path = _paper_visualizer_available()
    if viz_path is None:
        return None
    spec_module = importlib.util.spec_from_file_location("paper_visualizer", viz_path)
    mod = importlib.util.module_from_spec(spec_module)
    try:
        spec_module.loader.exec_module(mod)
    except Exception as e:
        print(f"[paper] failed to import visualizer: {e}", file=sys.stderr)
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    agent = mod.VisualizerAgent(output_dir=str(out_dir))

    t = spec["type"]
    cid = spec["id"]
    filename = f"{cid}.png"
    out_path = out_dir / filename

    try:
        if t in ("ree_pattern",):
            agent.generate_ree_pattern(
                elements=spec.get("elements", []),
                values=spec.get("values", []),
                title=spec.get("title", "REE Pattern"),
                filename=filename,
            )
        elif t in ("spider", "spider_diagram"):
            agent.generate_spider_diagram(
                elements=spec.get("elements", []),
                values=spec.get("values", []),
                title=spec.get("title", "Spider diagram"),
                filename=filename,
            )
        elif t in ("heatmap", "correlation_heatmap"):
            agent.generate_correlation_heatmap(
                data=spec.get("data", {}),
                title=spec.get("title", "Correlation heatmap"),
                filename=filename,
            )
        elif t in ("dendrogram", "cluster_dendrogram"):
            agent.generate_cluster_dendrogram(
                data=spec.get("data", {}),
                title=spec.get("title", "Cluster dendrogram"),
                filename=filename,
            )
        elif t == "boxplot":
            agent.generate_box_plot(
                data=spec.get("data", {}),
                title=spec.get("title", "Box plot"),
                filename=filename,
            )
        else:
            return None
    except Exception as e:
        print(f"[paper] render failed for {cid}: {e}", file=sys.stderr)
        return None

    return str(out_path) if out_path.exists() else None


def _render_lynai_chart(specs: list[dict], out_dir: Path) -> list[str]:
    """Delegate to lynai's render_chart.py for the supplied subset of specs."""
    if not specs:
        return []
    # Write a temp spec file containing just this subset, invoke render_chart.py
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(specs, tmp)
    tmp.close()
    try:
        result = subprocess.run(
            [sys.executable, str(HERE / "render_chart.py"), "--spec", tmp.name, "--out", str(out_dir)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            print(f"[lynai] render_chart.py exit {result.returncode}: {result.stderr}", file=sys.stderr)
        return [s["id"] for s in specs]
    finally:
        os.unlink(tmp.name)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LynAI chart factory dispatcher (v1.3, D-13)")
    p.add_argument("--spec", required=True, help="Path to chart_specs.json")
    p.add_argument("--out", required=True, help="Output directory for PNGs")
    args = p.parse_args(argv)

    specs = json.load(open(args.spec, encoding="utf-8"))
    out_dir = Path(args.out)

    by_backend: dict[str, list[dict]] = {"lynai": [], "paper": []}
    rejected: list[dict] = []
    for s in specs:
        # v1.4.2 D-16 P1-5: chart id sandbox — reject path-traversal IDs
        if not _validate_id(s):
            rejected.append({"id": s.get("id"), "reason": "INVALID_CHART_ID"})
            continue
        hint = s.get("backend", "auto")
        backend = _route(s.get("type", ""), hint)
        by_backend[backend].append(s)

    results = []

    # Lynai batch
    if by_backend["lynai"]:
        rendered = _render_lynai_chart(by_backend["lynai"], out_dir)
        results.extend({"id": cid, "backend": "lynai"} for cid in rendered)

    # Paper one-by-one
    paper_avail = _paper_visualizer_available() is not None
    for s in by_backend["paper"]:
        if not paper_avail:
            # Fallback: re-route to lynai as a bar chart
            print(f"[paper] visualizer not installed; routing {s['id']} to lynai/bar fallback", file=sys.stderr)
            fallback = dict(s, type="bar", backend="lynai")
            _render_lynai_chart([fallback], out_dir)
            results.append({"id": s["id"], "backend": "lynai_fallback"})
            continue
        path = _render_paper_chart(s, out_dir)
        results.append({"id": s["id"], "backend": "paper" if path else "failed"})

    # Summary
    log_path = out_dir / "chart_factory_log.json"
    log_path.write_text(json.dumps({"rendered": results}, indent=2))
    print(f"[ok] chart_factory: {len(results)} specs processed -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
