"""compositional.py — zero replacement + CLR/ILR log-ratio transform.

Default transform CLR (rank-deficient; for interpretation). ILR available
(full rank, default SBP) for ML. Zero/below-DL -> multiplicative replacement.
"""
import argparse, json, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from geochemlib import coda
from geochemlib.units import parse_column
from geochemlib.io_utils import write_summary

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_cfg():
    import yaml
    with open(os.path.join(HERE, "..", "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--elements", required=True, help="comma-separated element columns")
    ap.add_argument("--transform", default="clr", choices=["clr", "ilr"])
    args = ap.parse_args(argv)

    cfg = _load_cfg()["censored"]
    df = pd.read_csv(args.input)
    cols = [c.strip() for c in args.elements.split(",")]
    X = df[cols].to_numpy(dtype=float)
    X = np.nan_to_num(X, nan=0.0)

    affected = [cols[j] for j in range(X.shape[1]) if (X[:, j] <= 0).any()]
    # delta as fraction of closed total
    closed = X / np.where(X.sum(1, keepdims=True) == 0, 1, X.sum(1, keepdims=True))
    pos = closed[closed > 0]
    delta = cfg["delta_factor"] * (pos.min() if pos.size else 1e-6)
    Xr = coda.multiplicative_replacement(X, delta=delta)

    out = df.copy()
    if args.transform == "clr":
        Z = coda.clr(Xr)
        labels = [f"clr_{parse_column(c)[0]}" for c in cols]
    else:
        Z = coda.ilr(Xr)
        labels = [f"ilr_{i+1}" for i in range(Z.shape[1])]
    for j, lab in enumerate(labels):
        out[lab] = Z[:, j]
    out.to_csv(args.out, index=False)
    write_summary({"transform": args.transform,
                   "zero_replacement": {"method": cfg["coda_method"], "delta": float(delta),
                                        "affected_columns": affected}}, args.summary)
    print(json.dumps({"transform": args.transform, "affected": affected}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
