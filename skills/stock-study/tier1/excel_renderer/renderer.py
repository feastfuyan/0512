"""
C5 excel-renderer · openpyxl + jinja2.

Owner: 付岩

Public API:
  render(scores, alerts, narrative, regime, asof) -> Path
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from schemas.narratives import NarrativeResult
from schemas.scores import RiskAlert, StockScore


def render(
    scores: list[StockScore],
    alerts: list[RiskAlert],
    narrative: NarrativeResult,
    regime: str,
    asof: date,
    out_dir: Path = Path("output"),
) -> Path:
    """
    TODO (付岩 D1):
      - Port v1 Excel template into tier1/excel_renderer/templates/stockstudy.xlsx.j2
      - Render 5 sheets: Cover / Top10 / Bottom10 / AllScores / Disclaimer
      - Last sheet MUST contain full compliance/disclaimer.txt verbatim
      - Filename: StockStudy_{asof:%Y%m%d}_v3.2.xlsx
    """
    raise NotImplementedError("TODO 付岩: render")
