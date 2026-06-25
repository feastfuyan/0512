"""Product-dialect horizontal-bar SVG renderer with x-clamp overflow fix."""
from figure_spec import FigureSpec, format_label
from profiles.lynai_report import (
    NAVY,
    TEAL,
    LIGHT_GRAY,
    GROUP_TRANSLATE_Y_BASE,
    GROUP_TRANSLATE_Y_STEP,
    BAR_LABEL_X,
    BAR_LABEL_Y,
    BAR_BG_X,
    BAR_BG_Y,
    BAR_HEIGHT,
    BAR_BG_WIDTH,
    BAR_VALUE_LABEL_OFFSET,
    VIEWBOX_WIDTH,
    RIGHT_MARGIN,
    TITLE_Y,
    TITLE_FONT_SIZE,
    TITLE_FILL,
    LABEL_FONT_SIZE,
    LABEL_FILL,
    VALUE_LABEL_FONT_SIZE,
    VALUE_LABEL_FILL,
    SOURCE_NOTE_FONT_SIZE,
    SOURCE_NOTE_FILL,
    SOURCE_NOTE_Y_OFFSET,
)


def render_product_svg(fs: FigureSpec) -> str:
    """
    Render FigureSpec (product target, horizontal-bar) to product-dialect HTML SVG.

    Returns a <div class="chart-block"> with embedded <svg> in the mc-06 style:
    - One <g> per data row, with translate(40, i*42+10)
    - Background bar at x=180, value bar scaled to data
    - Value label clamped to prevent overflow (x <= 1040-45)
    - Deterministic: explicit sort by value descending

    Args:
        fs: FigureSpec with render_target="product", chart_type="horizontal-bar"

    Returns:
        str: HTML div with embedded SVG
    """
    # Sort data by value descending for determinism
    encoding = fs.encoding
    value_field = encoding.value_field
    sorted_data = sorted(fs.data, key=lambda row: row[value_field], reverse=True)

    # Find max value for bar scaling
    max_value = max(row[value_field] for row in sorted_data)

    # SVG dimensions: 1040 wide, height = num_rows * 42 + padding
    num_rows = len(sorted_data)
    svg_height = max(300, num_rows * GROUP_TRANSLATE_Y_STEP + 100)  # Minimum 300px for consistent sizing

    # Build SVG bars
    bar_groups = []
    for i, row in enumerate(sorted_data):
        label = row[encoding.label_field]
        value = row[value_field]

        # Scale bar width: value / max_value * 720
        bar_w = (value / max_value) * BAR_BG_WIDTH if max_value > 0 else 0

        # X position for value label, clamped to prevent overflow
        # min(180 + bar_w + 8, 1040 - 45) ensures text stays within viewBox margin
        label_x = min(BAR_BG_X + bar_w + BAR_VALUE_LABEL_OFFSET, VIEWBOX_WIDTH - RIGHT_MARGIN)

        # Format value label using shared format_label (M1); honors encoding.value_format
        value_label = format_label(value, encoding)

        # Build group with translate(40, i*42+10)
        translate_y = GROUP_TRANSLATE_Y_BASE + i * GROUP_TRANSLATE_Y_STEP
        group_svg = f'  <g transform="translate(40, {translate_y})">\n'

        # Category label (left side)
        group_svg += f'    <text x="{BAR_LABEL_X}" y="{BAR_LABEL_Y}" font-size="{LABEL_FONT_SIZE}" fill="{LABEL_FILL}">{label}</text>\n'

        # Background rect (light gray)
        group_svg += f'    <rect x="{BAR_BG_X}" y="{BAR_BG_Y}" width="{BAR_BG_WIDTH}" height="{BAR_HEIGHT}" fill="{LIGHT_GRAY}" rx="4"/>\n'

        # Value bar (teal)
        group_svg += f'    <rect x="{BAR_BG_X}" y="{BAR_BG_Y}" width="{bar_w}" height="{BAR_HEIGHT}" fill="{TEAL}" rx="4"/>\n'

        # Value label (clamped x)
        group_svg += f'    <text x="{label_x}" y="{BAR_LABEL_Y}" font-size="{VALUE_LABEL_FONT_SIZE}" fill="{VALUE_LABEL_FILL}">{value_label}</text>\n'

        group_svg += '  </g>\n'
        bar_groups.append(group_svg)

    # Build title
    title_svg = f'  <text x="20" y="{TITLE_Y}" font-size="{TITLE_FONT_SIZE}" font-weight="bold" fill="{TITLE_FILL}">{fs.title}</text>\n'

    # Build source note (positioned below chart)
    source_y = svg_height - SOURCE_NOTE_Y_OFFSET
    source_svg = f'  <text x="20" y="{source_y}" font-size="{SOURCE_NOTE_FONT_SIZE}" fill="{SOURCE_NOTE_FILL}">{fs.source_note}</text>\n'

    # Assemble SVG
    fig_id = fs.opts.fig_id if fs.opts.fig_id else "fig-unknown"
    svg_content = f"""<svg viewBox="0 0 {VIEWBOX_WIDTH} {svg_height}" xmlns="http://www.w3.org/2000/svg">
{title_svg}{''.join(bar_groups)}{source_svg}</svg>"""

    # Wrap in chart-block div
    html = f"""<div class="chart-block" id="{fig_id}" style="margin: 1rem 0;">
  <div style="margin-bottom: 0.5rem; font-weight: bold;">{fs.title}</div>
  {svg_content}
</div>"""

    return html
