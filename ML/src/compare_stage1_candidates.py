"""
Three Stage-1 label strategies, compared on ONE fixed yardstick. Candidates only.

THE QUESTION THIS IS BUILT TO ANSWER

  "Does the improvement come from better generalization, or just from changing
  the positive population?"

  Adding positives inflates PR-AUC mechanically, because PR-AUC depends on
  prevalence. A model trained on more positives, scored against more positives,
  looks better while having learned nothing extra. The only way to separate the
  two is to score every model on the SAME rows against the SAME target.

  So each model trains on its own labels, and all three are then evaluated on:
    1. a fixed yardstick - field-verified IHS labels, identical for all three
    2. WRI thermal plants - absent from every feature and every label here

  If a model wins on its own training target but not on those two, the gain is
  population, not generalization.

THE THREE MODELS

  M1 baseline   v1 features (NASA type-filtered) + FIRMS type2_fraction target
  M2 v2-IHS     v2 features (unfiltered)         + IHS-verified positives
  M3 v2-merged  v2 features (unfiltered)         + FIRMS union IHS positives

  M3 reintroduces NASA's flag as a POSITIVE LABEL SOURCE. It is never a
  feature, and it never defines negatives. That is a weaker dependency than
  production had, but it is a dependency, and it is reported as one.

CALIBRATION

  The v2 candidate was badly overconfident: predicted 0.977 against an observed
  0.683. Cause is the ~51x positive sample weighting. Every model here is
  wrapped in out-of-fold isotonic regression - inside each CV fold the training
  half is split again into fit and calibrate, so the calibrator never sees the
  test block. Raw and calibrated numbers are both reported.

Writes new files only. Promotes nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold, train_test_split

V1_FEATURES = Path("data/processed/hotspot_features_2025.csv")
V2_FEATURES = Path("data/processed/hotspot_features_2025_v2.csv")
IHS_FILE = Path("data/processed/ihs_points.csv")
OSM_FILE = Path("data/external/osm_features.csv")
PLANT_FILE = Path("data/external/power_plants.csv")

OUT_DIR = Path("models")
REPORT_OUT = OUT_DIR / "stage1_three_way_comparison.json"
SCORES_OUT = Path("data/processed/stage1_three_way_scores.csv")

EARTH_RADIUS_KM = 6371.0
BLOCK_SIZE = 20
N_SPLITS = 5
MATCH_KM = 4.0
CLEAR_KM = 10.0
PLANT_MATCH_KM = 2.0
CALIB_FRACTION = 0.20

FEATURES = [
    "total_detections", "active_days", "duty_cycle", "span_days",
    "longest_gap_days",
    "months_active", "month_cv", "peak_month_share",
    "night_fraction",
    "frp_mean", "frp_max", "frp_std", "frp_cv",
    "ti4_mean", "ti4_std", "ti5_mean", "ti4_minus_ti5_mean",
    "spread_km", "active_neighbours",
]
PARAMS = dict(max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
              min_samples_leaf=40, l2_regularization=1.0, random_state=42)
THERMAL_FUELS = {"Coal", "Gas", "Oil", "Petcoke", "Biomass", "Waste", "Cogeneration"}


def xyz(lat, lon):
    la, lo = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    return np.column_stack([np.cos(la) * np.cos(lo),
                            np.cos(la) * np.sin(lo), np.sin(la)])


def nearest_km(alat, alon, blat, blon):
    chord, _ = cKDTree(xyz(blat, blon)).query(xyz(alat, alon))
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2, 0, 1))


def precision_at_k(y, s, k=100):
    return float(np.asarray(y)[np.argsort(s)[::-1][:k]].mean())


def calibration_table(y, p, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.sum():
            rows.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(m.sum()),
                         "predicted": round(float(p[m].mean()), 4),
                         "observed": round(float(y[m].mean()), 4)})
    return rows


def max_calibration_gap(table):
    return round(max(abs(r["predicted"] - r["observed"]) for r in table), 4)


def build_frame():
    """One frame, one set of rows, every label variant attached."""
    v2 = pd.read_csv(V2_FEATURES)
    v1 = pd.read_csv(V1_FEATURES,
                     usecols=["cell_id", "type2_fraction"] + FEATURES)

    # Only cells present in BOTH, so all three models score identical rows.
    common = v2.merge(v1, on="cell_id", suffixes=("", "_v1"))
    print(f"v2 cells {len(v2):,}   v1 cells {len(v1):,}   common {len(common):,}")

    ihs = pd.read_csv(IHS_FILE)
    osm = pd.read_csv(OSM_FILE)
    pos_src, neg_src = ihs[ihs.Type == 0], ihs[ihs.Type == 1]

    km_pos = nearest_km(common.latitude, common.longitude, pos_src.latitude, pos_src.longitude)
    km_neg = nearest_km(common.latitude, common.longitude, neg_src.latitude, neg_src.longitude)
    km_ihs = nearest_km(common.latitude, common.longitude, ihs.latitude, ihs.longitude)
    km_osm = nearest_km(common.latitude, common.longitude, osm.latitude, osm.longitude)

    common["ihs_pos"] = (km_pos <= MATCH_KM) & (km_neg > MATCH_KM)
    common["ihs_neg"] = (km_neg <= MATCH_KM) & (km_pos > MATCH_KM)
    common["clear"] = (km_ihs > CLEAR_KM) & (km_osm > CLEAR_KM)

    # FIRMS positives, used ONLY as a label. type2_fraction is never a feature.
    common["firms_pos"] = common.type2_fraction >= 0.8
    common["firms_neg"] = common.type2_fraction <= 0.2

    # ---- the three targets ------------------------------------------------
    # M1: exactly production's definition.
    common["y_m1"] = np.where(common.firms_pos, 1,
                              np.where(common.firms_neg, 0, -1))
    # M2: field verification only, negatives are verified-or-clear.
    common["y_m2"] = np.where(common.ihs_pos, 1,
                              np.where(common.ihs_neg | common.clear, 0, -1))
    # M3: union of positives, same negatives as M2.
    common["y_m3"] = np.where(common.ihs_pos | common.firms_pos, 1,
                              np.where(common.ihs_neg | common.clear, 0, -1))

    # ---- the fixed yardstick, identical for all three ---------------------
    # Field-verified only. Independent of FIRMS by construction: 4,702 of these
    # positives are cells FIRMS types as vegetation.
    common["y_fixed"] = np.where(common.ihs_pos, 1,
                                 np.where(common.ihs_neg, 0, -1))
    return common


def run_model(df, target, feature_suffix, name):
    """Spatial-block CV with out-of-fold isotonic calibration."""
    cols = [f + feature_suffix for f in FEATURES]
    X = df[cols].rename(columns=dict(zip(cols, FEATURES)))
    y = df[target].to_numpy()
    trainable = y >= 0

    groups = ((np.floor(df.latitude / BLOCK_SIZE).astype(int) + 100) * 1000
              + np.floor(df.longitude / BLOCK_SIZE).astype(int))

    raw = np.full(len(df), np.nan)
    cal = np.full(len(df), np.nan)
    folds = []

    for i, (tr, te) in enumerate(
        GroupKFold(n_splits=N_SPLITS).split(X, np.where(trainable, y, 0), groups), 1
    ):
        tr = tr[trainable[tr]]
        if len(np.unique(y[tr])) < 2:
            continue
        # Split the TRAIN block again: the calibrator must never see test.
        fit_idx, cal_idx = train_test_split(
            tr, test_size=CALIB_FRACTION, random_state=42, stratify=y[tr])

        w = (y[fit_idx] == 0).sum() / max((y[fit_idx] == 1).sum(), 1)
        m = HistGradientBoostingClassifier(**PARAMS)
        m.fit(X.iloc[fit_idx], y[fit_idx],
              sample_weight=np.where(y[fit_idx] == 1, w, 1.0))

        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(m.predict_proba(X.iloc[cal_idx])[:, 1], y[cal_idx])

        p = m.predict_proba(X.iloc[te])[:, 1]
        raw[te] = p
        cal[te] = iso.predict(p)

        ok = te[trainable[te]]
        if len(np.unique(y[ok])) > 1:
            f = {"fold": i, "test_cells": int(len(ok)),
                 "positives": int(y[ok].sum()),
                 "pr_auc": round(float(average_precision_score(y[ok], raw[ok])), 4),
                 "roc_auc": round(float(roc_auc_score(y[ok], raw[ok])), 4)}
            folds.append(f)
            print(f"    fold {i}: PR-AUC {f['pr_auc']:.4f}  ROC {f['roc_auc']:.4f}  "
                  f"({f['positives']:,} pos / {len(ok):,})")
    return raw, cal, folds


def evaluate(df, raw, cal, folds, name, target):
    y_own = df[target].to_numpy()
    own = y_own >= 0
    fixed = df.y_fixed.to_numpy()
    fx = fixed >= 0

    pr = [f["pr_auc"] for f in folds]
    out = {
        "model": name,
        "train_positives": int((y_own == 1).sum()),
        "train_negatives": int((y_own == 0).sum()),
        "excluded": int((y_own == -1).sum()),
        "own_target": {
            "pr_auc_mean": round(float(np.mean(pr)), 4),
            "pr_auc_std": round(float(np.std(pr)), 4),
            "prec_at_100": round(precision_at_k(y_own[own], raw[own], 100), 4),
        },
        "fixed_yardstick": {
            "n": int(fx.sum()), "positives": int((fixed == 1).sum()),
            "pr_auc": round(float(average_precision_score(fixed[fx], raw[fx])), 4),
            "roc_auc": round(float(roc_auc_score(fixed[fx], raw[fx])), 4),
            "prec_at_100": round(precision_at_k(fixed[fx], raw[fx], 100), 4),
        },
        "spatial_folds": folds,
    }

    # Recall on verified positives at a false-positive rate matched on the
    # verified negatives - threshold-free comparison across models.
    vp = df.ihs_pos.to_numpy()
    vn = df.ihs_neg.to_numpy()
    rec = {}
    for fp_target in (0.05, 0.10, 0.20):
        t = float(np.nanquantile(raw[vn], 1 - fp_target))
        rec[f"fp_{int(fp_target*100)}pct"] = round(float(np.nanmean(raw[vp] >= t)), 4)
    out["recall_at_matched_fp"] = rec

    for label, scores in (("raw", raw), ("calibrated", cal)):
        m = own & ~np.isnan(scores)
        out[f"calibration_{label}"] = {
            "brier": round(float(brier_score_loss(y_own[m], scores[m])), 5),
            "max_gap": max_calibration_gap(calibration_table(y_own[m], scores[m])),
            "table": calibration_table(y_own[m], scores[m]),
        }
    return out


def wri_check(df, scores, plants):
    near = (nearest_km(df.latitude, df.longitude,
                       plants.latitude, plants.longitude) <= PLANT_MATCH_KM).astype(int)
    base = float(near.mean())
    ok = ~np.isnan(scores)
    s, n = scores[ok], near[ok]
    out = {"base_rate": round(base, 6)}
    for k in (100, 500, 1000):
        hit = float(n[np.argsort(s)[::-1][:k]].mean())
        out[f"top{k}"] = round(hit, 4)
        out[f"lift{k}"] = round(hit / base, 1)
    return out


def main():
    df = build_frame()
    plants = pd.read_csv(PLANT_FILE, low_memory=False)
    plants = plants[plants.primary_fuel.isin(THERMAL_FUELS)].dropna(
        subset=["latitude", "longitude"])

    print("\nLabel counts per strategy:")
    for t, name in (("y_m1", "M1 baseline (FIRMS)"),
                    ("y_m2", "M2 v2 + IHS"),
                    ("y_m3", "M3 v2 + FIRMS u IHS")):
        v = df[t]
        print(f"  {name:24s} pos {int((v==1).sum()):>7,}   "
              f"neg {int((v==0).sum()):>8,}   excluded {int((v==-1).sum()):>7,}")
    print(f"  fixed yardstick          pos {int((df.y_fixed==1).sum()):>7,}   "
          f"neg {int((df.y_fixed==0).sum()):>8,}")

    results, all_scores = [], {}
    specs = [("M1_baseline_v1_firms", "y_m1", "_v1"),
             ("M2_v2_ihs", "y_m2", ""),
             ("M3_v2_merged", "y_m3", "")]

    for name, target, suffix in specs:
        print(f"\n=== {name} ===")
        raw, cal, folds = run_model(df, target, suffix, name)
        r = evaluate(df, raw, cal, folds, name, target)
        r["independent_wri"] = wri_check(df, raw, plants)
        results.append(r)
        all_scores[name] = raw
        print(f"    fixed yardstick PR-AUC {r['fixed_yardstick']['pr_auc']:.4f}  "
              f"ROC {r['fixed_yardstick']['roc_auc']:.4f}   "
              f"WRI top500 {r['independent_wri']['lift500']}x")

    print("\n" + "=" * 78)
    print("HEAD TO HEAD")
    print("=" * 78)
    print(f"{'model':22s} {'own PR-AUC':>18s} {'FIXED PR-AUC':>13s} {'FIXED ROC':>10s} "
          f"{'WRI@500':>9s} {'Brier(cal)':>11s}")
    for r in results:
        o = r["own_target"]; f = r["fixed_yardstick"]
        print(f"{r['model']:22s} {o['pr_auc_mean']:.4f}+/-{o['pr_auc_std']:.4f}  "
              f"{f['pr_auc']:13.4f} {f['roc_auc']:10.4f} "
              f"{r['independent_wri']['lift500']:8.1f}x {r['calibration_calibrated']['brier']:11.5f}")

    print("\nRecall on field-verified positives at matched false-positive rates:")
    print(f"{'model':22s} {'FP 5%':>8s} {'FP 10%':>8s} {'FP 20%':>8s}")
    for r in results:
        v = r["recall_at_matched_fp"]
        print(f"{r['model']:22s} {v['fp_5pct']:8.1%} {v['fp_10pct']:8.1%} {v['fp_20pct']:8.1%}")

    print("\nCalibration, worst gap between predicted and observed:")
    for r in results:
        print(f"  {r['model']:22s} raw {r['calibration_raw']['max_gap']:.3f}  ->  "
              f"isotonic {r['calibration_calibrated']['max_gap']:.3f}")

    out = pd.DataFrame({"cell_id": df.cell_id, "latitude": df.latitude,
                        "longitude": df.longitude, "y_fixed": df.y_fixed})
    for k, v in all_scores.items():
        out[k] = v
    out.to_csv(SCORES_OUT, index=False)

    REPORT_OUT.write_text(json.dumps({
        "question": "Better generalization, or just a bigger positive population?",
        "method": ("Each model trains on its own labels, then all three are scored on "
                   "one fixed field-verified yardstick and on WRI, which is absent "
                   "from every feature and every label."),
        "promoted": False,
        "m3_dependency_note": (
            "M3 uses FIRMS type2_fraction to define part of its POSITIVE set. It is "
            "never a feature and never defines negatives, but it is a real "
            "reintroduction of NASA classification as a label source."
        ),
        "results": results,
    }, indent=2), encoding="utf-8")
    print(f"\nReport: {REPORT_OUT}\nScores: {SCORES_OUT}\nNothing promoted.")


if __name__ == "__main__":
    main()
