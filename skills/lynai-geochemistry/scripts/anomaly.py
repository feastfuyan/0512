"""anomaly.py — single-element robust thresholds, spatial KNN local background,
multi-element robust (MCD) Mahalanobis on ILR, and weighted pathfinder score.

DEPENDENCY ORDER (G11): multi-element anomaly runs on ILR log-ratios, NOT raw
ppm. We compute ILR internally before MCD Mahalanobis. ILR (isometric log-ratio)
produces full-rank (D-1) coordinates — avoids the singular-covariance warnings
that CLR triggers in sklearn's MinCovDet. ILR is isometric to CLR for Aitchison
distances, so Mahalanobis results are mathematically equivalent.

Optional contamination / spatial-control screen (G14 hardening):
  --contam-coords "E,N"    known source point; flags elements whose concentration
                           decays with Euclidean distance (rho <= -0.5, p < 0.05).
  --contam-covariate <col> existing proximity column in CSV; flags elements
                           strongly correlated with it (|rho| >= 0.5, p < 0.05).
Both can be given together. If neither is given, the screen is silently skipped.
"""
import argparse, json, os, sys, warnings
import math
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from geochemlib import coda, spatial, robust_mahalanobis as rmaha, pathfinder
from geochemlib.robust_stats import robust_threshold
from geochemlib.units import parse_column
from geochemlib.io_utils import write_summary
from geochemlib.censoring import detect_dl_floor


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--elements", required=True)
    ap.add_argument("--coords", default=None, help="Easting,Northing")
    ap.add_argument("--method", default="mad")
    ap.add_argument("--spatial-mode", default="none", choices=["none", "knn"])
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--pathfinder", default=None)
    ap.add_argument("--contam-coords", default=None,
                    help='Known contamination source "E,N" (same projection as --coords). '
                         'Flags elements whose concentration decays with distance (rho<=-0.5, p<0.05).')
    ap.add_argument("--contam-covariate", default=None,
                    help="Existing proximity covariate column in CSV. "
                         "Flags elements strongly correlated with it (|rho|>=0.5, p<0.05).")
    args = ap.parse_args(argv)

    df = pd.read_csv(args.input)
    cols = [c.strip() for c in args.elements.split(",")]
    out = df.copy()
    summary = {"single_element": {}, "multi_element": {}, "spatial": args.spatial_mode}

    # 1) single-element robust thresholds + spatial local background
    norm_anoms = {}
    coords = None
    if args.coords:
        cx, cy = [c.strip() for c in args.coords.split(",")]
        coords = df[[cx, cy]].to_numpy(dtype=float)
    for col in cols:
        el = parse_column(col)[0]
        res = robust_threshold(df[col].to_numpy(dtype=float), method=args.method, log=True)
        out[f"{el}_anom_global"] = res["flags"]
        exceedances = int(np.asarray(res["flags"]).sum())
        note = res["note"]
        if exceedances == 0 and not note:
            note = "0 samples exceeded threshold"
        summary["single_element"][el] = {"method_used": res["method_used"],
                                          "threshold": res["threshold"],
                                          "exceedances": exceedances,
                                          "threshold_space": "log",
                                          "note": note}
        # normalized anomaly magnitude (z-like) for pathfinder
        v = np.log(np.where(df[col] > 0, df[col], np.nan))
        z = (v - np.nanmedian(v)) / (np.nanstd(v) + 1e-9)
        norm_anoms[el] = np.nan_to_num(z)
        if args.spatial_mode == "knn" and coords is not None:
            _, local = spatial.knn_local_background(coords, df[col].to_numpy(dtype=float), k=args.k)
            out[f"{el}_anom_local"] = local

    # 2) multi-element: CLR -> MCD robust Mahalanobis (G11 order)
    # Use ALL numeric element columns (not just --elements) so that immobile
    # elements (e.g. Zr) act as a compositional anchor — geochemically required
    # for CLR to distinguish mobile-element halos from flat background.
    all_elem_cols = [c for c in df.columns if parse_column(c)[1] is not None]
    maha_cols = all_elem_cols if len(all_elem_cols) > len(cols) else cols
    X = df[maha_cols].to_numpy(dtype=float)
    X = np.where(X > 0, X, np.nan)
    X = np.nan_to_num(X, nan=np.nanmin(X[X > 0]) if (X > 0).any() else 1e-6)
    Z = coda.ilr(X)
    p = Z.shape[1]                       # = d-1 ilr dims
    n = Z.shape[0]
    n_over_p = n / p if p > 0 else 0.0
    maha_note = ""
    if n_over_p < 5:
        maha_note = "low n/p (<5): MCD covariance unreliable; treat maha_robust as indicative only"
    # Fix D: suppress noisy MCD RuntimeWarnings (targeted — only around the MCD call)
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            d = rmaha.robust_mahalanobis(Z, random_state=0)
        estimator = "MCD"
    except Exception as e:               # MCD can fail when n is too small for the support
        d = rmaha.classic_mahalanobis(Z)
        estimator = "classic_fallback"
        maha_note = (maha_note + "; " if maha_note else "") + f"MCD failed ({type(e).__name__}); used classic"
    out["maha_robust"] = d

    # Fix C: detect DL-floor pile-up in the composition columns
    dl_floor_cols = []
    for mc in maha_cols:
        floor_val, _ = detect_dl_floor(df[mc].to_numpy(dtype=float))
        if floor_val is not None:
            dl_floor_cols.append(mc)
    if dl_floor_cols:
        dl_note = f"; DL-floor pile-up in composition: {dl_floor_cols} — MCD may be distorted"
        maha_note = (maha_note + dl_note) if maha_note else dl_note.lstrip("; ")

    summary["multi_element"] = {"transform": "ilr", "estimator": estimator,
                                "composition_cols": maha_cols,
                                "n_over_p": round(float(n_over_p), 2),
                                "note": maha_note,
                                "dl_floor_cols": dl_floor_cols,
                                "median": float(np.median(d))}

    # 3) pathfinder weighted score
    if args.pathfinder:
        score = pathfinder.pathfinder_score(norm_anoms, system=args.pathfinder, renormalize=True)
        out[f"pathfinder_{args.pathfinder}"] = score
        summary["pathfinder"] = {"system": args.pathfinder}

    # 4) contamination / spatial-control screen (optional, additive, G14 hardening)
    if args.contam_coords or args.contam_covariate:
        summary["contamination_screen"] = _run_contam_screen(
            df=df, cols=cols,
            contam_coords_str=args.contam_coords,
            covariate_col=args.contam_covariate,
            coords_str=args.coords,
            multi_element_summary=summary["multi_element"],
        )

    out.to_csv(args.out, index=False)
    write_summary(summary, args.summary)
    print(json.dumps({"spatial": args.spatial_mode, "n": len(df)}))
    return 0


def _run_contam_screen(df, cols, contam_coords_str, covariate_col,
                        coords_str, multi_element_summary):
    """Compute Spearman correlation-based contamination / spatial-control screen.

    Parameters
    ----------
    df               : input DataFrame
    cols             : list of element column names (already harmonised)
    contam_coords_str: "E,N" string or None
    covariate_col    : column name string or None
    coords_str       : "cx,cy" columns string (required when contam_coords_str given)
    multi_element_summary : the multi_element dict (mutated in place if majority flagged)

    Returns
    -------
    dict : contamination_screen block
    """
    screen = {}

    # ---- determine mode ----
    do_coords = contam_coords_str is not None
    do_covariate = covariate_col is not None

    if do_coords and do_covariate:
        screen["mode"] = "coords+covariate"
    elif do_coords:
        screen["mode"] = "coords"
    else:
        screen["mode"] = "covariate"

    # ---- parse / validate source coords ----
    dist_from_source = None
    if do_coords:
        if coords_str is None:
            raise ValueError(
                "--contam-coords requires --coords (Easting,Northing columns must be specified)"
            )
        try:
            src_e, src_n = [float(v.strip()) for v in contam_coords_str.split(",")]
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"--contam-coords must be two floats separated by a comma, got: {contam_coords_str!r}"
            ) from exc
        cx_col, cy_col = [c.strip() for c in coords_str.split(",")]
        dist_from_source = np.sqrt(
            (df[cx_col].to_numpy(dtype=float) - src_e) ** 2
            + (df[cy_col].to_numpy(dtype=float) - src_n) ** 2
        )
        screen["source_coords"] = [src_e, src_n]

    # ---- validate covariate column ----
    if do_covariate:
        if covariate_col not in df.columns:
            raise ValueError(
                f"--contam-covariate column {covariate_col!r} not found in CSV. "
                f"Available columns: {list(df.columns)}"
            )
        screen["covariate"] = covariate_col

    # ---- per-element Spearman ----
    per_element = {}
    MIN_PAIRS = 5

    def _spearman_result(el_col, x_vals, basis_label):
        """Return dict with rho, p, flag for one element vs one covariate array."""
        el_vals = df[el_col].to_numpy(dtype=float)
        # drop NaN pairs
        mask = np.isfinite(el_vals) & np.isfinite(x_vals)
        n_valid = int(mask.sum())
        if n_valid < MIN_PAIRS:
            return {
                "spearman_rho": None,
                "p_value": None,
                "flag": False,
                "basis": basis_label,
                "note": f"only {n_valid} valid pairs (< {MIN_PAIRS}); not tested",
            }
        rho, pval = spearmanr(el_vals[mask], x_vals[mask])
        return {
            "spearman_rho": round(float(rho), 4),
            "p_value": round(float(pval), 6),
            "flag": False,   # set below per mode
            "basis": basis_label,
        }

    for col in cols:
        results_for_col = []

        if do_coords and dist_from_source is not None:
            r = _spearman_result(col, dist_from_source, "distance_from_source")
            # flag: rho <= -0.5 AND p < 0.05  (concentration decays away from source)
            if r["p_value"] is not None:
                r["flag"] = (r["spearman_rho"] <= -0.5) and (r["p_value"] < 0.05)
            results_for_col.append(r)

        if do_covariate:
            cov_vals = df[covariate_col].to_numpy(dtype=float)
            r2 = _spearman_result(col, cov_vals, f"covariate:{covariate_col}")
            # flag: |rho| >= 0.5 AND p < 0.05
            if r2["p_value"] is not None:
                r2["flag"] = (abs(r2["spearman_rho"]) >= 0.5) and (r2["p_value"] < 0.05)
            results_for_col.append(r2)

        # merge: flag if ANY basis flags
        if len(results_for_col) == 1:
            per_element[col] = results_for_col[0]
        else:
            # coords+covariate — keep both bases; combined flag = OR
            combined_flag = any(r["flag"] for r in results_for_col)
            per_element[col] = {
                "flag": combined_flag,
                "coords_result": results_for_col[0],
                "covariate_result": results_for_col[1],
            }

    screen["per_element"] = per_element
    n_flagged = sum(1 for v in per_element.values() if v["flag"])
    n_elements = len(cols)
    screen["n_flagged"] = n_flagged
    screen["n_elements"] = n_elements

    # build source label for assessment string
    if do_coords and do_covariate:
        source_label = f"source({contam_coords_str}) and covariate({covariate_col})"
    elif do_coords:
        source_label = f"source({contam_coords_str})"
    else:
        source_label = f"covariate({covariate_col})"

    screen["assessment"] = (
        f"{n_flagged}/{n_elements} elements strongly spatially controlled by "
        f"{source_label} — anomalies may be dispersion/contamination, "
        "not in-situ mineralisation (G14)"
    )

    # append note to multi_element if majority flagged
    if n_elements > 0 and n_flagged >= math.ceil(n_elements / 2):
        existing_note = multi_element_summary.get("note") or ""
        append = (
            f"; contamination screen: majority of elements spatially controlled by "
            f"{source_label} — review for non-mineralised origin (G14)"
        )
        multi_element_summary["note"] = (existing_note + append).lstrip("; ")

    return screen


if __name__ == "__main__":
    sys.exit(main())
