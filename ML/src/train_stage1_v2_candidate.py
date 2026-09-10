"""
Stage 1 candidate v2 - no NASA classification anywhere. CANDIDATE ONLY.

WHAT CHANGED FROM PRODUCTION

  features  built by build_hotspot_dataset_v2.py, which never reads the
            fire_type column at all. Production computed every feature on
            detections NASA had typed 0 or 2, so `total_detections` meant
            "detections NASA approved". It now means what it says.

  target    field-verified IHS records instead of type2_fraction. Production
            learned to reproduce NASA's flag; on the cells where both have an
            opinion that flag disagrees with field verification 57% of the time.

  inputs    static_probability appears nowhere. It was the laundering path -
            a scalar trained on NASA's flag, fed forward as a feature.

THE NEGATIVE-LABEL PROBLEM, AND HOW IT IS HANDLED

  Dropping type2_fraction also drops our only source of negatives. IHS supplies
  just 592 verified ones - too few and too specific to represent "ordinary
  vegetation fire". So negatives are of two kinds and are reported separately:

    verified negative  IHS Type 1: a person checked and it is not industrial.
    presumed negative  no IHS object within 10 km AND no mapped OSM industrial
                       feature within 10 km. Not proof, but a cell with no
                       industrial infrastructure anywhere near it is
                       overwhelmingly likely to be burning vegetation.

  Using OSM and IHS to CONSTRUCT labels is permitted; using them as model
  inputs is not, and neither appears in the feature matrix.

  WRI is deliberately absent from the label logic as well, so it remains the
  one evaluation set nothing in this project has ever learned from.

Writes only new files. Promotes nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

FEATURES_FILE = Path("data/processed/hotspot_features_2025_v2.csv")
IHS_FILE = Path("data/processed/ihs_points.csv")
OSM_FILE = Path("data/external/osm_features.csv")
PLANT_FILE = Path("data/external/power_plants.csv")

MODEL_OUT = Path("models/stage1_v2_candidate.joblib")
REPORT_OUT = Path("models/stage1_v2_candidate_report.json")
SCORES_OUT = Path("data/processed/stage1_v2_scores.csv")

EARTH_RADIUS_KM = 6371.0
BLOCK_SIZE = 20
N_SPLITS = 5

MATCH_KM = 4.0        # an IHS object and a 0.05 deg cell are the same place
CLEAR_KM = 10.0       # nothing industrial within this = presumed negative
PLANT_MATCH_KM = 2.0

# Byte-identical to production. The comparison must isolate the data change.
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
    chord, idx = cKDTree(xyz(blat, blon)).query(xyz(alat, alon))
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2, 0, 1)), idx


def precision_at_k(y, s, k=100):
    return float(np.asarray(y)[np.argsort(s)[::-1][:k]].mean())


def build(df):
    ihs = pd.read_csv(IHS_FILE)
    osm = pd.read_csv(OSM_FILE)
    pos_src, neg_src = ihs[ihs.Type == 0], ihs[ihs.Type == 1]

    km_pos, _ = nearest_km(df.latitude, df.longitude, pos_src.latitude, pos_src.longitude)
    km_neg, _ = nearest_km(df.latitude, df.longitude, neg_src.latitude, neg_src.longitude)
    km_ihs, _ = nearest_km(df.latitude, df.longitude, ihs.latitude, ihs.longitude)
    km_osm, _ = nearest_km(df.latitude, df.longitude, osm.latitude, osm.longitude)

    df["y"] = -1
    df["label_kind"] = "ambiguous"

    verified_pos = (km_pos <= MATCH_KM) & (km_neg > MATCH_KM)
    verified_neg = (km_neg <= MATCH_KM) & (km_pos > MATCH_KM)
    presumed_neg = (km_ihs > CLEAR_KM) & (km_osm > CLEAR_KM)

    df.loc[presumed_neg, ["y", "label_kind"]] = [0, "presumed_negative"]
    df.loc[verified_neg, ["y", "label_kind"]] = [0, "verified_negative"]
    df.loc[verified_pos, ["y", "label_kind"]] = [1, "verified_positive"]
    return df


def calibration(y, p, bins=10):
    """Reliability table: does a predicted 0.7 actually happen 70% of the time?"""
    edges = np.linspace(0, 1, bins + 1)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.sum() == 0:
            continue
        rows.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(m.sum()),
                     "mean_predicted": round(float(p[m].mean()), 4),
                     "observed_rate": round(float(y[m].mean()), 4)})
    return rows


def main():
    df = pd.read_csv(FEATURES_FILE)
    print(f"v2 cells: {len(df):,}")
    df = build(df)

    counts = df.label_kind.value_counts()
    print("\nLabel construction:")
    for k, v in counts.items():
        print(f"  {k:20s} {v:>9,}")

    train = df[df.y >= 0].reset_index(drop=True)
    y = train.y.to_numpy()
    print(f"\nTrainable cells: {len(train):,}   positive rate {y.mean():.3%}")

    groups = ((np.floor(train.latitude / BLOCK_SIZE).astype(int) + 100) * 1000
              + np.floor(train.longitude / BLOCK_SIZE).astype(int))
    print(f"Spatial blocks: {groups.nunique()}  ->  {N_SPLITS}-fold block CV\n")

    X = train[FEATURES]
    oof = np.zeros(len(train))
    folds = []
    for i, (tr, te) in enumerate(GroupKFold(n_splits=N_SPLITS).split(X, y, groups), 1):
        w = (y[tr] == 0).sum() / max((y[tr] == 1).sum(), 1)
        m = HistGradientBoostingClassifier(**PARAMS)
        m.fit(X.iloc[tr], y[tr], sample_weight=np.where(y[tr] == 1, w, 1.0))
        oof[te] = m.predict_proba(X.iloc[te])[:, 1]
        f = {"fold": i, "test_cells": int(len(te)), "test_positives": int(y[te].sum()),
             "pr_auc": round(float(average_precision_score(y[te], oof[te])), 4),
             "roc_auc": round(float(roc_auc_score(y[te], oof[te])), 4),
             "prec_at_100": round(precision_at_k(y[te], oof[te], 100), 4)}
        folds.append(f)
        print(f"  fold {i}: PR-AUC {f['pr_auc']:.4f}  ROC {f['roc_auc']:.4f}  "
              f"p@100 {f['prec_at_100']:.2f}  ({f['test_positives']:,} pos / {len(te):,})")

    pr = np.mean([f["pr_auc"] for f in folds])
    pr_sd = np.std([f["pr_auc"] for f in folds])
    print(f"\n=== Held-out regions: PR-AUC {pr:.4f} +/- {pr_sd:.4f} ===")

    overall = {
        "pr_auc_mean": round(float(pr), 4),
        "pr_auc_std": round(float(pr_sd), 4),
        "pr_auc_pooled": round(float(average_precision_score(y, oof)), 4),
        "roc_auc_pooled": round(float(roc_auc_score(y, oof)), 4),
        "prec_at_100": round(precision_at_k(y, oof, 100), 4),
        "prec_at_500": round(precision_at_k(y, oof, 500), 4),
        "brier": round(float(brier_score_loss(y, oof)), 5),
    }
    print(f"  pooled PR-AUC {overall['pr_auc_pooled']:.4f}   "
          f"p@100 {overall['prec_at_100']:.2f}   p@500 {overall['prec_at_500']:.2f}   "
          f"Brier {overall['brier']:.5f}")

    # Recall at operating thresholds, on the verified positives only.
    vp = (train.label_kind == "verified_positive").values
    vn = (train.label_kind == "verified_negative").values
    print("\nRecall on the 12,905 field-verified positives:")
    recall = {}
    for t in (0.5, 0.7, 0.9):
        r = float((oof[vp] >= t).mean())
        fp = float((oof[vn] >= t).mean())
        recall[str(t)] = {"recall_verified_pos": round(r, 4),
                          "fp_rate_verified_neg": round(fp, 4)}
        print(f"  threshold {t:.1f}:  recall {r:6.1%}   "
              f"false-positive rate on verified negatives {fp:6.1%}")

    print("\nCalibration (predicted vs observed):")
    cal = calibration(y, oof)
    for r in cal:
        print(f"  {r['bin']}  n={r['n']:>8,}  predicted {r['mean_predicted']:.3f}  "
              f"observed {r['observed_rate']:.3f}")

    # ---- Independent WRI check --------------------------------------------
    plants = pd.read_csv(PLANT_FILE, low_memory=False)
    plants = plants[plants.primary_fuel.isin(THERMAL_FUELS)].dropna(
        subset=["latitude", "longitude"])
    km_plant, _ = nearest_km(train.latitude, train.longitude,
                             plants.latitude, plants.longitude)
    near_plant = (km_plant <= PLANT_MATCH_KM).astype(int)
    base = float(near_plant.mean())
    wri = {"base_rate": round(base, 6)}
    print(f"\nIndependent WRI check (never used in features OR labels), "
          f"base rate {base:.4%}:")
    for k in (100, 500, 1000):
        hit = float(near_plant[np.argsort(oof)[::-1][:k]].mean())
        wri[f"top{k}"] = round(hit, 4)
        wri[f"lift{k}"] = round(hit / base, 1)
        print(f"  top{k:<5} {hit:.3f}  ({hit/base:.1f}x)")

    # ---- Shortcut audit: can any single feature carry the label alone? -----
    print("\nSingle-feature shortcut scan (ROC-AUC of each feature alone):")
    single = {}
    for f in FEATURES:
        v = train[f].fillna(train[f].median()).to_numpy()
        a = roc_auc_score(y, v)
        single[f] = round(float(max(a, 1 - a)), 4)
    for f, a in sorted(single.items(), key=lambda kv: -kv[1])[:6]:
        flag = "  <-- inspect" if a >= 0.90 else ""
        print(f"  {f:22s} {a:.4f}{flag}")

    # ---- Save --------------------------------------------------------------
    w = (y == 0).sum() / max((y == 1).sum(), 1)
    final = HistGradientBoostingClassifier(**PARAMS)
    final.fit(X, y, sample_weight=np.where(y == 1, w, 1.0))
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": final, "features": FEATURES,
                 "target": "field-verified IHS industrial vs presumed/verified negative",
                 "version": "stage1 / v2 candidate - NOT promoted"}, MODEL_OUT)

    train["score"] = oof
    train[["cell_id", "latitude", "longitude", "y", "label_kind", "score"]].to_csv(
        SCORES_OUT, index=False)

    REPORT_OUT.write_text(json.dumps({
        "candidate": str(MODEL_OUT),
        "promoted": False,
        "production_untouched": "models/hotspot_static_source_model.joblib",
        "removed": ["fire_type filter (column no longer read at all)",
                    "type2_fraction target", "static_probability feature"],
        "features": FEATURES,
        "label_construction": {k: int(v) for k, v in counts.items()},
        "trainable_cells": int(len(train)),
        "positive_rate": round(float(y.mean()), 5),
        "cv": f"GroupKFold {N_SPLITS} over {BLOCK_SIZE}-degree blocks",
        "folds": folds,
        "overall": overall,
        "recall_at_threshold": recall,
        "calibration": cal,
        "independent_wri": wri,
        "single_feature_auc": single,
        "caveat": (
            "Not directly comparable with the 0.902 production PR-AUC: that was "
            "measured against NASA's own type flag on a NASA-filtered population. "
            "This is measured against field-verified labels on the full population. "
            "Different question, different denominator."
        ),
    }, indent=2), encoding="utf-8")

    print(f"\nCandidate : {MODEL_OUT}")
    print(f"Report    : {REPORT_OUT}")
    print("Nothing promoted.")


if __name__ == "__main__":
    main()
