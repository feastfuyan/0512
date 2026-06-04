"""normalize.py — chondrite/shale normalization + REE anomalies (Eu*/Ce*).

Reference set is pinned and version-tagged (default Sun & McDonough 1989).
"""
import argparse, json, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from geochemlib import reference_data as rd
from geochemlib.units import parse_column
from geochemlib.io_utils import write_summary


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--ref", default="chondrite")
    args = ap.parse_args(argv)

    ref_meta = rd.get_reference(args.ref)
    ref = ref_meta["values"]
    df = pd.read_csv(args.input)

    # map element -> column (assume harmonized ppm columns)
    el_cols = {}
    for col in df.columns:
        el, unit = parse_column(col)
        if unit is not None and el in ref:
            el_cols[el] = col

    out = df.copy()
    for el, col in el_cols.items():
        out[f"{el}_n"] = df[col] / ref[el]

    # Eu/Eu*, Ce/Ce* per row — geometric if both neighbours present, else fallback
    ree_meta = {}

    def _ree(el, geo_a, geo_b, fb_a, fb_b, fb_name, coeffs):
        if all(x in el_cols for x in (el, geo_a, geo_b)):
            ne = df[el_cols[el]] / ref[el]
            na = df[el_cols[geo_a]] / ref[geo_a]
            nb = df[el_cols[geo_b]] / ref[geo_b]
            out[f"{el}_anom"] = ne / np.sqrt(na * nb)
            ree_meta[el] = {"computed": True, "method": "geometric"}
        elif all(x in el_cols for x in (el, fb_a, fb_b)):
            ne = df[el_cols[el]] / ref[el]
            na = df[el_cols[fb_a]] / ref[fb_a]
            nb = df[el_cols[fb_b]] / ref[fb_b]
            out[f"{el}_anom"] = ne / (coeffs[0] * na + coeffs[1] * nb)
            ree_meta[el] = {"computed": True, "method": fb_name}
        else:
            ree_meta[el] = {"computed": False,
                            "reason": f"needs ({geo_a},{geo_b}) or fallback ({fb_a},{fb_b}); none present"}

    _ree("Eu", "Sm", "Gd", "Sm", "Tb", "fallback_SmTb", (0.67, 0.33))
    _ree("Ce", "La", "Pr", "La", "Nd", "fallback_LaNd", (0.5, 0.5))

    out.to_csv(args.out, index=False)
    write_summary({"reference": {"name": args.ref, "source": ref_meta["source"],
                                 "version": ref_meta["version"]},
                   "normalized_elements": list(el_cols),
                   "ree_anomalies": ree_meta}, args.summary)
    print(json.dumps({"reference": ref_meta["version"], "elements": list(el_cols)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
