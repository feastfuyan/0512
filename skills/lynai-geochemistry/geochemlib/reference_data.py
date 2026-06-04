"""Pinned normalization reference sets. Default CI chondrite = Sun & McDonough (1989).

Citation: Sun, S.-s. & McDonough, W.F. (1989) Chemical and isotopic systematics
of oceanic basalts. Geol. Soc. Spec. Pub. 42, 313-345.
Values are CI carbonaceous chondrite, ppm.
"""
import numpy as np

REE_ORDER = ["La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd",
             "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu"]

# PROVENANCE: CI chondrite, Sun & McDonough (1989), Geol. Soc. Spec. Pub. 42, Table.
# NOTE: two value sets circulate under "SM89"; this is the self-consistent A-set
# (Yb 0.170 / Lu 0.0254). Verify against the paper Table before any external comparison.
_CHONDRITE_SM89 = {
    "La": 0.237, "Ce": 0.612, "Pr": 0.095, "Nd": 0.467, "Sm": 0.153,
    "Eu": 0.058, "Gd": 0.2055, "Tb": 0.0374, "Dy": 0.254, "Ho": 0.0566,
    "Er": 0.1655, "Tm": 0.0255, "Yb": 0.170, "Lu": 0.0254,
}

# Post-Archean Australian Shale (Taylor & McLennan 1985), ppm — for sediment normalization.
_PAAS_TM85 = {
    "La": 38.2, "Ce": 79.6, "Pr": 8.83, "Nd": 33.9, "Sm": 5.55,
    "Eu": 1.08, "Gd": 4.66, "Tb": 0.774, "Dy": 4.68, "Ho": 0.991,
    "Er": 2.85, "Tm": 0.405, "Yb": 2.82, "Lu": 0.433,
}

_REFERENCES = {
    "chondrite": {"source": "Sun & McDonough 1989", "version": "SM89_v1", "values": _CHONDRITE_SM89},
    "paas": {"source": "Taylor & McLennan 1985", "version": "TM85_v1", "values": _PAAS_TM85},
}


def get_reference(name):
    key = name.lower()
    if key not in _REFERENCES:
        raise KeyError(f"unknown reference set {name!r}; have {list(_REFERENCES)}")
    return _REFERENCES[key]


def normalize(sample, reference="chondrite"):
    """sample: dict element->ppm. Returns dict element->normalized value."""
    ref = get_reference(reference)["values"]
    return {el: sample[el] / ref[el] for el in sample if el in ref}


def ree_anomaly(sample, element, reference="chondrite", method="auto"):
    """Eu/Eu* and Ce/Ce*. method: 'auto' uses the geometric-mean neighbour formula when
    both neighbours are present, else a linear-interpolation fallback (for missing/below-DL
    Gd or Pr). 'geometric' forces the standard formula."""
    n = normalize(sample, reference)
    if element == "Eu":
        if "Sm" in n and "Gd" in n and method in ("auto", "geometric"):
            return n["Eu"] / np.sqrt(n["Sm"] * n["Gd"])
        if method == "auto" and "Sm" in n and "Tb" in n:
            return n["Eu"] / (0.67 * n["Sm"] + 0.33 * n["Tb"])   # [ref: Taylor & McLennan 1985]
        raise ValueError("Eu anomaly needs (Sm,Gd) or fallback (Sm,Tb)")
    if element == "Ce":
        if "La" in n and "Pr" in n and method in ("auto", "geometric"):
            return n["Ce"] / np.sqrt(n["La"] * n["Pr"])
        if method == "auto" and "La" in n and "Nd" in n:
            return n["Ce"] / (0.5 * n["La"] + 0.5 * n["Nd"])
        raise ValueError("Ce anomaly needs (La,Pr) or fallback (La,Nd)")
    raise ValueError(f"unsupported anomaly element {element!r}")
