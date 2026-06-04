"""feature_engineer.py — FROZEN IO-contract skeleton (Phase 1).

Assembles a block-structured feature matrix for lyn-models. This is NOT a
production-grade feature selector (Phase 4); it only freezes the schema so the
ML side has a stable contract. Raw columns are tagged non-model to avoid
re-introducing closure/collinearity (anti-leakage).

Label semantics v1: label column is categorical in {prospective, barren} or a
numeric distance-to-known-mineralization; chosen by --label-column / --label-kind.
"""
import argparse, json, os, sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from geochemlib.units import parse_column
from geochemlib.io_utils import write_summary

META = {"SampleID", "Easting", "Northing", "Lon", "Lat"}


def classify_columns(cols):
    blocks = {"meta": [], "raw": [], "ratio": [], "logratio": [], "anomaly": [], "pathfinder": [], "label": []}
    for c in cols:
        lc = c.lower()
        if c in META:
            blocks["meta"].append(c)
        elif lc.startswith(("clr_", "ilr_", "alr_")):
            blocks["logratio"].append(c)
        elif "anom" in lc or lc == "maha_robust":
            blocks["anomaly"].append(c)
        elif lc.startswith("pathfinder_"):
            blocks["pathfinder"].append(c)
        elif "/" in c or lc.endswith("_ratio"):
            blocks["ratio"].append(c)
        elif parse_column(c)[1] is not None:
            blocks["raw"].append(c)
    return blocks


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--label-column", default="")
    ap.add_argument("--label-kind", default="categorical", choices=["categorical", "distance"])
    args = ap.parse_args(argv)

    df = pd.read_csv(args.input)
    blocks = classify_columns(list(df.columns))
    if args.label_column and args.label_column in df.columns:
        blocks["label"] = [args.label_column]

    # ordered feature matrix: meta, then model features (logratio+ratio+anomaly+pathfinder), raw last (tagged)
    ordered = (blocks["meta"] + blocks["logratio"] + blocks["ratio"]
               + blocks["anomaly"] + blocks["pathfinder"] + blocks["label"] + blocks["raw"])
    df[ordered].to_csv(args.out, index=False)
    write_summary({"status": "skeleton", "label_semantics_version": "v1",
                   "label_kind": args.label_kind, "schema": blocks,
                   "model_feature_blocks": ["logratio", "ratio", "anomaly", "pathfinder"],
                   "non_model_blocks": ["raw"]}, args.summary)
    print(json.dumps({"status": "skeleton", "n_features": len(ordered)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
