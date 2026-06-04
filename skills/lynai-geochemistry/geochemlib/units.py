"""Element/unit parsing and harmonization to a common mass basis (default ppm)."""
import re

class InvalidUnitError(ValueError):
    pass

# mass-fraction conversion factors to ppm
_TO_PPM = {
    "pct": 1e4, "percent": 1e4, "%": 1e4,
    "ppm": 1.0, "gpt": 1.0, "g/t": 1.0, "ppmw": 1.0,
    "ppb": 1e-3, "ppbw": 1e-3,
}
_UNIT_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)[_\s]+(pct|percent|%|ppm|ppmw|gpt|g/t|ppb|ppbw)$", re.I)


def parse_column(col):
    """Return (element, unit_lower) or (col, None) if no recognised unit suffix."""
    m = _UNIT_RE.match(col.strip())
    if m:
        return m.group(1), m.group(2).lower()
    return col, None


def to_ppm_factor(unit):
    if unit is None:
        raise InvalidUnitError("missing unit; refuse to guess")
    u = unit.lower()
    if u not in _TO_PPM:
        raise InvalidUnitError(f"unknown unit: {unit!r}")
    return _TO_PPM[u]


def harmonize_value(value, unit):
    """Return (value_in_ppm, factor)."""
    f = to_ppm_factor(unit)
    return value * f, f
