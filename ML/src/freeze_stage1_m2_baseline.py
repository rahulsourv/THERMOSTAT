"""
Freeze M2 as the Stage-1 research baseline. NOT a production promotion.

M2 is the fully independent variant: no NASA classification reaches the
features or the Stage-1 target by any path. It matched the old baseline on the
fixed field-verified yardstick (ROC 0.8131 vs 0.8093), so independence costs
nothing measurable - which is what makes it a defensible thing to freeze.

DISCRIMINATION AND CALIBRATION ARE KEPT APART

  The benchmark is measured on RAW model output. Isotonic regression is a
  monotone transform, so it cannot change ranking - PR-AUC, ROC-AUC and
  precision@k are identical before and after, and quoting "calibrated PR-AUC"
  would imply a gain that does not exist.

  So the calibrator is fitted and stored as a SEPARATE artefact. Discrimination
  numbers come from the raw scores; calibration numbers describe the
  calibrator. Nothing in this file mixes them.

  The calibrator is fitted out-of-fold: inside each spatial block, the training
  half is split again into fit and calibrate, so the calibrator never sees the
  block it is scoring.

Population: all 690,872 cells from hotspot_features_2025_v2.csv. Deliberately
NOT the v1-intersection used during comparison - a frozen independent baseline
must not depend on the deprecated NASA-filtered feature table.
"""

from __future__ import annotations

import hashlib
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

FEATURES_FILE = Path("data/processed/hotspot_features_2025_v2.csv")
IHS_FILE = Path("data/processed/ihs_points.csv")
OSM_FILE = Path("data/external/osm_features.csv")
PLANT_FILE = Path("data/external/power_plants.csv")

MODEL_OUT = Path("models/stage1_m2_baseline.joblib")
CALIB_OUT = Path("models/stage1_m2_calibrator.joblib")
SPEC_OUT = Path("models/stage1_m2_baseline_spec.json")
SCORES_OUT = Path("data/processed/stage1_m2_scores.csv")

EARTH_RADIUS_KM = 6371.0
BLOCK_SIZE = 20
N_SPLITS = 5
MATCH_KM = 4.0
CLEAR_KM = 10.0
PLANT_MATCH_KM = 2.0
CALIB_FRACTION = 0.20
SEED = 42

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
              min_samples_leaf=40, l2_regularization=1.0, random_state=SEED)
THERMAL_FUELS = {"Coal", "Gas", "Oil", "Petcoke", "Biomass", "Waste", "Cogeneration"}


def xyz(lat, lon):
    la, lo = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    return np.column_stack([np.cos(la) * np.cos(lo),
                            np.cos(la) * np.sin(lo), np.sin(la)])


def nearest_km(alat, alon, blat, blon):
    chord, _ = cKDTree(xyz(blat, blon)).query(xyz(alat, alon))
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2, 0, 1))


def precision_at_k(y, s, k):
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


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def main():
    df = pd.read_csv(FEATURES_FILE)
    ihs = pd.read_csv(IHS_FILE)
    osm = pd.read_csv(OSM_FILE)
    pos_src, neg_src = ihs[ihs.Type == 0], ihs[ihs.Type == 1]

    km_pos = nearest_km(df.latitude, df.longitude, pos_src.latitude, pos_src.longitude)
    km_neg = nearest_km(df.latitude, df.longitude, neg_src.latitude, neg_src.longitude)
    km_ihs = nearest_km(df.latitude, df.longitude, ihs.latitude, ihs.longitude)
    km_osm = nearest_km(df.latitude, df.longitude, osm.latitude, osm.longitude)

    verified_pos = (km_pos <= MATCH_KM) & (km_neg > MATCH_KM)
    verified_neg = (km_neg <= MATCH_KM) & (km_pos > MATCH_KM)
    clear = (km_ihs > CLEAR_KM) & (km_osm > CLEAR_KM)

    df["y"] = -1
    df.loc[clear, "y"] = 0
    df.loc[verified_neg, "y"] = 0
    df.loc[verified_pos, "y"] = 1
    df["is_verified_pos"] = verified_pos
    df["is_verified_neg"] = verified_neg

    train = df[df.y >= 0].reset_index(drop=True)
    y = train.y.to_numpy()
    X = train[FEATURES]
    groups = ((np.floor(train.latitude / BLOCK_SIZE).astype(int) + 100) * 1000
              + np.floor(train.longitude / BLOCK_SIZE).astype(int))

    print(f"Population   : {len(df):,} cells")
    print(f"Trainable    : {len(train):,}   positives {int(y.sum()):,} "
          f"({y.mean():.3%})")
    print(f"Spatial blocks: {groups.nunique()}  ->  {N_SPLITS}-fold\n")

    raw = np.zeros(len(train))
    cal = np.zeros(len(train))
    folds, drifts = [], []

    for i, (tr, te) in enumerate(GroupKFold(n_splits=N_SPLITS).split(X, y, groups), 1):
        fit_idx, cal_idx = train_test_split(
            tr, test_size=CALIB_FRACTION, random_state=SEED, stratify=y[tr])
        w = (y[fit_idx] == 0).sum() / max((y[fit_idx] == 1).sum(), 1)
        m = HistGradientBoostingClassifier(**PARAMS)
        m.fit(X.iloc[fit_idx], y[fit_idx],
              sample_weight=np.where(y[fit_idx] == 1, w, 1.0))

        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(m.predict_proba(X.iloc[cal_idx])[:, 1], y[cal_idx])

        p = m.predict_proba(X.iloc[te])[:, 1]
        raw[te], cal[te] = p, iso.predict(p)

        # Isotonic is WEAKLY monotone: it never reverses an ordering, but it
        # does map distinct raw scores onto one calibrated value. ROC scores a
        # tie at half credit, so merging a pair that was previously ordered
        # WRONGLY (zero credit) nudges AUC up, and merging a correctly ordered
        # pair nudges it down. The movement can therefore go either way, and
        # the meaningful invariant is that it is negligible - not its sign.
        if len(np.unique(y[te])) > 1:
            fold_drift = abs(roc_auc_score(y[te], cal[te]) - roc_auc_score(y[te], p))
            assert fold_drift < 1e-3, (
                f"fold {i}: calibration moved ranking by {fold_drift}, far more "
                "than tie-merging can explain - the calibrator is suspect")
            drifts.append(fold_drift)

        f = {"fold": i, "test_cells": int(len(te)), "positives": int(y[te].sum()),
             "pr_auc": round(float(average_precision_score(y[te], p)), 4),
             "roc_auc": round(float(roc_auc_score(y[te], p)), 4),
             "prec_at_100": round(precision_at_k(y[te], p, 100), 4)}
        folds.append(f)
        print(f"  fold {i}: PR-AUC {f['pr_auc']:.4f}  ROC {f['roc_auc']:.4f}  "
              f"p@100 {f['prec_at_100']:.2f}")

    pr = [f["pr_auc"] for f in folds]

    # ---- DISCRIMINATION: raw scores only ---------------------------------
    discrimination = {
        "measured_on": "RAW model output (isotonic is monotone and cannot change ranking)",
        "pr_auc_mean": round(float(np.mean(pr)), 4),
        "pr_auc_std": round(float(np.std(pr)), 4),
        "pr_auc_pooled": round(float(average_precision_score(y, raw)), 4),
        "roc_auc_pooled": round(float(roc_auc_score(y, raw)), 4),
        "prec_at_100": round(precision_at_k(y, raw, 100), 4),
        "prec_at_500": round(precision_at_k(y, raw, 500), 4),
        "spatial_folds": folds,
    }
    vp, vn = train.is_verified_pos.to_numpy(), train.is_verified_neg.to_numpy()
    discrimination["recall_at_matched_fp"] = {
        f"fp_{int(t*100)}pct": round(float((raw[vp] >= np.quantile(raw[vn], 1 - t)).mean()), 4)
        for t in (0.05, 0.10, 0.20)
    }

    plants = pd.read_csv(PLANT_FILE, low_memory=False)
    plants = plants[plants.primary_fuel.isin(THERMAL_FUELS)].dropna(
        subset=["latitude", "longitude"])
    near = (nearest_km(train.latitude, train.longitude,
                       plants.latitude, plants.longitude) <= PLANT_MATCH_KM).astype(int)
    base = float(near.mean())
    discrimination["independent_wri"] = {"base_rate": round(base, 6), **{
        f"lift{k}": round(float(near[np.argsort(raw)[::-1][:k]].mean()) / base, 1)
        for k in (100, 500, 1000)}}

    print(f"\nDISCRIMINATION (raw)  PR-AUC {discrimination['pr_auc_mean']:.4f} "
          f"+/- {discrimination['pr_auc_std']:.4f}   "
          f"p@100 {discrimination['prec_at_100']:.2f}   "
          f"WRI@500 {discrimination['independent_wri']['lift500']}x")

    # ---- CALIBRATION: reported separately, never mixed in -----------------
    raw_tbl, cal_tbl = calibration_table(y, raw), calibration_table(y, cal)
    gap = lambda t: round(max(abs(r["predicted"] - r["observed"]) for r in t), 4)
    calibration = {
        "method": "isotonic regression, fitted out-of-fold on a 20% split of each training block",
        "note": "Does not affect discrimination. Ranking metrics above are unchanged by it.",
        "brier_raw": round(float(brier_score_loss(y, raw)), 6),
        "brier_calibrated": round(float(brier_score_loss(y, cal)), 6),
        "max_gap_raw": gap(raw_tbl),
        "max_gap_calibrated": gap(cal_tbl),
        "reliability_raw": raw_tbl,
        "reliability_calibrated": cal_tbl,
    }
    print(f"CALIBRATION (separate) Brier {calibration['brier_raw']:.5f} -> "
          f"{calibration['brier_calibrated']:.5f}   "
          f"max gap {calibration['max_gap_raw']:.3f} -> "
          f"{calibration['max_gap_calibrated']:.3f}")

    pooled_drift = abs(roc_auc_score(y, raw) - roc_auc_score(y, cal))
    calibration["max_per_fold_roc_drift_from_ties"] = round(float(max(drifts)), 8)
    calibration["pooled_roc_drift_from_per_fold_calibrators"] = round(float(pooled_drift), 6)
    calibration["ranking_note"] = (
        "Isotonic never reverses an ordering, but it merges distinct scores into "
        "ties, and ROC gives a tie half credit - so AUC can shift a negligible "
        "amount in either direction. Asserted per fold below 1e-3. The pooled "
        "figure moves a little more because each fold carries its own "
        "calibrator; the SHIPPED calibrator is a single isotonic fitted on all "
        "out-of-fold scores. Discrimination is quoted from RAW scores "
        "throughout, so none of this touches the benchmark."
    )
    print(f"  ranking preserved: worst per-fold drift {max(drifts):.2e} "
          f"(tie-merging); pooled {pooled_drift:.5f} (separate calibrators)")

    # ---- Persist model and calibrator as SEPARATE artefacts ---------------
    w = (y == 0).sum() / max((y == 1).sum(), 1)
    final = HistGradientBoostingClassifier(**PARAMS)
    final.fit(X, y, sample_weight=np.where(y == 1, w, 1.0))
    joblib.dump({"model": final, "features": FEATURES,
                 "version": "stage1 / M2 research baseline (frozen)"}, MODEL_OUT)

    iso_final = IsotonicRegression(out_of_bounds="clip")
    iso_final.fit(raw, y)          # fitted on out-of-fold scores, not in-sample
    joblib.dump({"calibrator": iso_final,
                 "fitted_on": "out-of-fold raw scores from the frozen protocol",
                 "apply_to": "raw predict_proba output of stage1_m2_baseline.joblib"},
                CALIB_OUT)

    train["score_raw"] = raw
    train["score_calibrated"] = cal
    train[["cell_id", "latitude", "longitude", "y", "is_verified_pos",
           "is_verified_neg", "score_raw", "score_calibrated"]].to_csv(
        SCORES_OUT, index=False)

    SPEC_OUT.write_text(json.dumps({
        "name": "Stage 1 - M2 research baseline",
        "status": "FROZEN research baseline. NOT promoted to production.",
        "production_model_still": "models/hotspot_static_source_model.joblib",
        "frozen_on": "2026-09-07",
        "artefacts": {
            "model": str(MODEL_OUT),
            "calibrator": str(CALIB_OUT),
            "scores": str(SCORES_OUT),
            "feature_table": str(FEATURES_FILE),
            "feature_table_sha256_16": file_digest(FEATURES_FILE),
            "builder": "src/build_hotspot_dataset_v2.py",
        },
        "independence_guarantees": [
            "NASA fire_type is NOT used in features. build_hotspot_dataset_v2.py "
            "does not even read the column from disk.",
            "NASA fire_type is NOT used in the Stage-1 label. The target is "
            "field-verified IHS records (POI + high-resolution imagery).",
            "type2_fraction is excluded entirely - it is neither computed nor stored "
            "by the v2 builder.",
            "static_probability is excluded from every feature matrix. It was the "
            "path by which a NASA-trained scalar re-entered downstream models.",
            "IHS membership and IHS missingness are NOT predictive features. IHS is "
            "used only to construct labels. Its decade columns were tested and "
            "rejected: present for 1.37% of cells, and that subset is 87.4% positive "
            "against 0.099% elsewhere, so the model would read the label off "
            "missingness.",
            "WRI is absent from features AND labels, so it remains a genuinely "
            "independent evaluation set.",
            "latitude, longitude, first_doy and last_doy remain excluded - latitude "
            "alone once scored 0.922 AUC by memorising oil-field geography.",
        ],
        "features": FEATURES,
        "n_features": len(FEATURES),
        "label_definition": {
            "positive": f"IHS Type 0 (field-verified industrial) within {MATCH_KM} km",
            "negative_verified": f"IHS Type 1 (field-verified NOT industrial) within {MATCH_KM} km",
            "negative_presumed": f"no IHS object AND no OSM industrial feature within {CLEAR_KM} km",
            "excluded": "everything else (ambiguous)",
        },
        "evaluation_protocol": {
            "cv": f"GroupKFold, {N_SPLITS} folds",
            "blocks": f"{BLOCK_SIZE}-degree spatial blocks",
            "seed": SEED,
            "discrimination_measured_on": "raw scores",
            "calibration_measured_separately": True,
            "independent_check": "WRI thermal plants within 2 km, never trained on",
        },
        "discrimination": discrimination,
        "calibration": calibration,
        "population": {
            "cells": int(len(df)),
            "trainable": int(len(train)),
            "positives": int(y.sum()),
            "negatives": int((y == 0).sum()),
            "excluded_ambiguous": int((df.y == -1).sum()),
        },
        "known_limitations": [
            "Fold-level PR-AUC ranges roughly 0.54-0.79; regional performance is uneven "
            "and the mean hides that.",
            "Most negatives are presumed rather than verified - only 592 negatives were "
            "checked by a person.",
            "No live inference: scores are precomputed per cell and joined by cell_id, "
            "so a location with no 2025 history gets no prediction.",
        ],
    }, indent=2), encoding="utf-8")

    print(f"\nFrozen spec : {SPEC_OUT}")
    print(f"Model       : {MODEL_OUT}")
    print(f"Calibrator  : {CALIB_OUT}  (separate artefact)")
    print("\nStage-1 experimentation closed. Production untouched.")


if __name__ == "__main__":
    main()
