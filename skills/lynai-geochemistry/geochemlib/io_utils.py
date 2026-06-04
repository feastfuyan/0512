"""CSV loading and JSON-safe summary writing."""
import json
import numpy as np
import pandas as pd
from geochemlib.units import parse_column


def load_geochem_csv(path):
    """Return (df, elems) where elems is a list of (element, unit) for unit-bearing columns."""
    df = pd.read_csv(path)
    elems = []
    for col in df.columns:
        el, unit = parse_column(col)
        if unit is not None:
            elems.append((el, unit))
    return df, elems


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _jsonable(obj.tolist())
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def write_summary(summary, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_jsonable(summary), f, ensure_ascii=False, indent=2)
