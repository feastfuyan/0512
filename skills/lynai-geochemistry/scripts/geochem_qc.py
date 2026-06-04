"""geochem_qc.py — QAQC gate + unit harmonization + censoring detection.

Single source of truth for: unit harmonization (-> config units.harmonize_to),
non-detect detection (isotope-safe, per column), and machine-executable QC
thresholds (blank/CRM/duplicate/drift). Emits cleaned CSV + qc_summary JSON.
Exit code is 0 even on QC failure (the JSON carries pass=false); the AGENT
enforces the STOP. Only true errors (bad units) exit non-zero.
"""
import argparse
import json
import sys
import os
import yaml
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from geochemlib import units, censoring
from geochemlib.io_utils import write_summary

HERE = os.path.dirname(os.path.abspath(__file__))


def load_config(path=None):
    cfg_path = path or os.path.join(HERE, "..", "config.yaml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--qc-config", default=None, help="JSON with crm_cert + blank_dl")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    iso_tokens = cfg["isotopes"]["tokens"]
    qc = cfg["qc"]
    harmonize_to = cfg["units"]["harmonize_to"]
    on_fail = cfg["units"]["on_parse_fail"]
    qc_aux = json.loads(open(args.qc_config).read()) if args.qc_config else {}
    crm_cert = qc_aux.get("crm_cert", {})
    blank_dl = qc_aux.get("blank_dl", {})

    df = pd.read_csv(args.input)
    summary = {"qc_summary": {"pass": True, "failed_rules": []},
               "unit_conversions": [], "censored": {}, "qc_warnings": []}
    failed = summary["qc_summary"]["failed_rules"]

    sample_type = df["SampleType"].astype(str).str.lower() if "SampleType" in df else None
    clean = df.copy()
    # Track harmonized numeric values per element for DL-floor pass (Fix #5)
    harmonized_vals = {}   # el -> np.ndarray of harmonized floats

    # iterate element columns
    for col in list(df.columns):
        el, unit = units.parse_column(col)
        if unit is None:
            continue
        # 1) censoring detection (isotope-safe)
        try:
            flags, vals = censoring.detect_censored(df[col], col_name=col, iso_tokens=iso_tokens)
        except ValueError as e:
            print(f"ERROR detecting censoring in {col}: {e}", file=sys.stderr)
            return 2
        if flags.sum() > 0:
            summary["censored"][el] = {"count": int(flags.sum()),
                                       "method": cfg["censored"]["univariate_method"]}
        # 2) unit harmonization
        try:
            factor = units.to_ppm_factor(unit) if harmonize_to == "ppm" else None
        except units.InvalidUnitError as e:
            if on_fail == "error":
                print(f"ERROR: {e} in column {col}", file=sys.stderr)
                return 2
            factor = 1.0
        new_unit = harmonize_to
        new_col = f"{el}_{new_unit}"
        clean[new_col] = vals.to_numpy(dtype=float) * factor
        harmonized_vals[el] = clean[new_col].to_numpy(dtype=float)
        if new_col != col:
            clean.drop(columns=[col], inplace=True, errors="ignore")
            summary["unit_conversions"].append({"from": col, "to": new_col, "factor": factor})

        # 3) QC threshold checks against the (harmonized) values
        if sample_type is not None:
            hv = clean[new_col]
            # blank contamination: blank value < blank_max_multiple_dl * DL
            if col in blank_dl or el in blank_dl:
                dl = blank_dl.get(col, blank_dl.get(el))
                dl_ppm = dl * factor
                blanks = hv[sample_type == "blank"]
                if (blanks > qc["blank_max_multiple_dl"] * dl_ppm).any():
                    if not any(f["rule"] == "blank_contamination" for f in failed):
                        failed.append({"rule": "blank_contamination", "count": int((blanks > qc["blank_max_multiple_dl"] * dl_ppm).sum())})
            # CRM recovery
            for sid, certs in crm_cert.items():
                if col in certs or el in certs:
                    cert_val = certs.get(col, certs.get(el)) * factor
                    meas = clean.loc[df["SampleID"] == sid, new_col]
                    if len(meas):
                        rec = float(meas.iloc[0]) / cert_val if cert_val else np.nan
                        lo, hi = qc["crm_recovery"]
                        if not (lo <= rec <= hi):
                            failed.append({"rule": "crm_recovery", "count": 1,
                                           "detail": {"sample": sid, "element": el, "recovery": round(rec, 3)}})

    if failed:
        summary["qc_summary"]["pass"] = False

    # Fix #5: DL-floor detection (pile-up at positive column minimum)
    # Run on harmonized values AFTER explicit censoring; skip elements already
    # recorded via explicit '<DL' text detection.
    for el, hvals in harmonized_vals.items():
        if el in summary["censored"]:
            continue   # already recorded via explicit '<DL' detection
        floor, count = censoring.detect_dl_floor(hvals.tolist())
        if floor is not None:
            summary["censored"][el] = {
                "count": count,
                "method": "dl_floor_suspected",
                "floor": float(floor),
            }
            summary["qc_warnings"].append(
                f"{el}: suspected DL floor at {floor} "
                f"({count} samples at positive column minimum — "
                "lab may have reported below-DL values as the DL value)"
            )

    # Fix #4: warn when no QC sample types present and no crm_cert/blank_dl supplied
    QC_TYPES = {"blank", "crm", "field_dup", "pulp_dup", "duplicate", "standard"}
    has_qc_samples = (
        sample_type is not None
        and sample_type.str.lower().isin(QC_TYPES).any()
    )
    has_qc_config = bool(crm_cert or blank_dl)
    if not has_qc_samples and not has_qc_config:
        summary["qc_warnings"].append(
            "no QC material (blank/CRM/duplicate) inserted — "
            "accuracy/precision NOT independently verifiable"
        )

    clean.to_csv(args.out, index=False)
    write_summary(summary, args.summary)
    print(json.dumps(summary["qc_summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
