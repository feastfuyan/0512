"""LynAI Report color and geometry profile for product-dialect rendering."""

# Colors from LynAI brand palette (navy/gold for text, teal for bars)
NAVY = "#1F3864"
GOLD = "#B8860B"
TEAL = "#14b8a6"
LIGHT_GRAY = "#f1f5f9"

# Horizontal-bar geometry (from mc-06.html.j2)
GROUP_TRANSLATE_Y_BASE = 10  # pixels for first bar group
GROUP_TRANSLATE_Y_STEP = 42  # pixels between bar groups (height per row)
BAR_LABEL_X = 0  # x position for category label
BAR_LABEL_Y = 22  # y position for category label (baseline)
BAR_BG_X = 180  # x position for bar background rect
BAR_BG_Y = 6  # y position for bar background rect (top)
BAR_HEIGHT = 22  # height of bar (both bg and value rect)
BAR_BG_WIDTH = 720  # width of bar background (max width for value bar)
BAR_VALUE_LABEL_OFFSET = 8  # gap between bar right-edge and label
VIEWBOX_WIDTH = 1040  # fixed SVG viewBox width
RIGHT_MARGIN = 45  # right margin to clamp text: min(label_x, 1040-45)

# Title styling
TITLE_Y = 20
TITLE_FONT_SIZE = 16
TITLE_FONT_WEIGHT = "bold"
TITLE_FILL = NAVY

# Text styling (labels, values, axes)
LABEL_FONT_SIZE = 12
LABEL_FILL = NAVY
VALUE_LABEL_FONT_SIZE = 12
VALUE_LABEL_FILL = NAVY

# Source note styling
SOURCE_NOTE_FONT_SIZE = 10
SOURCE_NOTE_FILL = "#666666"
SOURCE_NOTE_Y_OFFSET = 30  # pixels below chart
