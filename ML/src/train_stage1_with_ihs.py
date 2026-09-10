"""
Stage 1, retrained with field-verified IHS labels. ABLATION ONLY - promotes nothing.

WHY THIS EXISTS

  Our stage-1 labels come from NASA's FIRMS `type` field: a cell is positive
  if >=80% of its detections are type 2. Joining the Ma et al. IHS dataset to
  our cells shows that flag is badly incomplete. On the 8,210 cells where both
  sources have an opinion:

        FIRMS says vegetation, IHS verified industrial : 4,702
        FIRMS says industrial,  IHS verified industrial : 3,082
        FIRMS says vegetation, IHS verified NOT        :   412
        FIRMS says industrial,  IHS verified NOT        :    14

  They agree only 42.6% of the time, and the disagreement is almost entirely
  one-directional: FIRMS misses industrial sources that people have physically
  verified. Our 0.902 PR-AUC was measured against those incomplete labels.

WHAT THIS MEANS FOR THE COMPARISON

  A model trained on better labels may score WORSE against FIRMS labels while
  being genuinely better, because it correctly flags sources FIRMS mislabels.
  So FIRMS agreement is not the yardstick here. Both models are scored on the
  same held-out FIELD-VERIFIED IHS cells, which is the only label set in this
  project produced by people looking at the ground.

PROTECTING THE INDEPENDENT VALIDATION

  IHS objects within 2 km of a WRI power plant are excluded from training
  entirely. The WRI register is the one check in this project that no model
  has ever trained on, and it stays that way - otherwise the headline
  "68x lift, independently confirmed" claim quietly becomes circular.

Outputs (all NEW files - nothing existing is overwritten):
  models/hotspot_static_source_model_v3.joblib
  models/stage1_ihs_comparison.json
  data/processed/stage1_merged_labels.csv
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from scipy.spatial import cKDTree
from sklearn.metrics import average_precision_score, roc_auc_score

from sklearn.model_selection import GroupKFold

FEATURES_FILE = Path("data/processed/hotspot_features_2025.csv")
IHS_FILE = Path("data/processed/ihs_points.csv")

MODEL_OUT = Path("models/hotspot_static_source_model_v3.joblib")
REPORT_OUT = Path("models/stage1_ihs_comparison.json")
LABELS_OUT = Path("data/processed/stage1_merged_labels.csv")
PLANT_FILE = Path("data/external/power_plants.csv")

EARTH_RADIUS_KM = 6371.0
PLANT_MATCH_KM = 2.0
# Only fuels that actually burn something show up on a thermal sensor.
THERMAL_FUELS = {"Coal", "Gas", "Oil", "Petcoke", "Biomass", "Waste", "Cogeneration"}

BLOCK_SIZE = 20
N_SPLITS = 5

CELL_MATCH_KM = 4.0     # an IHS object and one of our 0.05 deg cells coincide
WRI_GUARD_KM = 2.0      # keep the WRI validation independent

# Identical to the production stage-1 model, so the comparison isolates the
# effect of the LABELS and nothing else. Still no latitude or longitude.
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


def precision_at_k(y_true, scores, k=100):
    order = np.argsort(scores)[::-1][:k]
    return float(np.asarray(y_true)[order].mean())


def build_labels() -> pd.DataFrame:
    feat = pd.read_csv(FEATURES_FILE)
    ihs = pd.read_csv(IHS_FILE)

    usable = ihs[
        (ihs.km_to_our_place <= CELL_MATCH_KM)
        & (ihs.km_to_plant > WRI_GUARD_KM)
        & (ihs.Type.isin([0, 1]))
    ]

    # One cell can catch several IHS objects. Where they disagree we simply
    # do not know, so the cell is dropped rather than resolved by a coin flip.
    grouped = usable.groupby("our_cell_id").Type.agg(["nunique", "min"])
    clean = grouped[grouped["nunique"] == 1].copy()
    clean["ihs_label"] = (clean["min"] == 0).astype(int)   # Type 0 = industrial
    dropped_conflicts = int((grouped["nunique"] > 1).sum())

    feat = feat.merge(clean[["ihs_label"]], left_on="cell_id",
                      right_index=True, how="left")

    # Field verification outranks a satellite product's own flag.
    feat["merged_label"] = np.where(
        feat.ihs_label.notna(), feat.ihs_label, feat.label
    )
    feat["label_origin"] = np.where(feat.ihs_label.notna(), "ihs", "firms")

    # -1 is FIRMS' "mixed cell, do not train on this"
    feat = feat[feat.merged_label.isin([0, 1])].copy()
    feat["merged_label"] = feat.merged_label.astype(int)
    feat["firms_label"] = feat.label

    print(f"Cells with a usable label: {len(feat):,}")
    print(f"  from field-verified IHS : {int((feat.label_origin=='ihs').sum()):,}")
    print(f"  from the FIRMS type flag: {int((feat.label_origin=='firms').sum()):,}")
    print(f"  conflicting cells dropped: {dropped_conflicts:,}")
    print(f"\nmerged positive rate: {feat.merged_label.mean():.3%}")
    return feat, dropped_conflicts


def run(df, label_col, train_mask, name):
    """Spatial-block CV. Returns out-of-fold scores for every row in df.

    train_mask selects which rows a model is allowed to LEARN from; every row
    is still scored, so the two models can be compared on identical test sets.
    """
    X = df[FEATURES]
    y = df[label_col].values
    groups = (
        (np.floor(df.latitude / BLOCK_SIZE).astype(int) + 100) * 1000
        + np.floor(df.longitude / BLOCK_SIZE).astype(int)
    )
    oof = np.zeros(len(df))

    for fold, (tr, te) in enumerate(
        GroupKFold(n_splits=N_SPLITS).split(X, y, groups), start=1
    ):
        tr = tr[train_mask.values[tr]]          # honour the training filter
        y_tr = y[tr]
        if len(np.unique(y_tr)) < 2:
            continue
        weight = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)
        model = HistGradientBoostingClassifier(**PARAMS)
        model.fit(X.iloc[tr], y_tr,
                  sample_weight=np.where(y_tr == 1, weight, 1.0))
        oof[te] = model.predict_proba(X.iloc[te])[:, 1]
        print(f"    {name} fold {fold}: trained on {len(tr):,}, scored {len(te):,}")
    return oof


def score_on(mask, y_true, scores, label):
    """PR-AUC / ROC-AUC / precision@100 on one evaluation subset."""
    y, s = y_true[mask], scores[mask]
    if len(np.unique(y)) < 2:
        return None
    return {
        "subset": label,
        "n": int(mask.sum()),
        "positives": int(y.sum()),
        "pr_auc": round(float(average_precision_score(y, s)), 4),
        "roc_auc": round(float(roc_auc_score(y, s)), 4),
        "prec_at_100": round(precision_at_k(y, s, 100), 4),
    }


def wri_check(df, scores, name):
    """The one evaluation neither model has ever trained on.

    IHS objects near a WRI plant were held out of training precisely so this
    stays honest. Prevalence here is ~0.2%, so top-k precision is the
    meaningful read - and it is directly comparable between models.
    """
    plants = pd.read_csv(PLANT_FILE, low_memory=False)
    plants = plants[plants.primary_fuel.isin(THERMAL_FUELS)]
    plants = plants.dropna(subset=["latitude", "longitude"])

    def xyz(lat, lon):
        la, lo = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
        return np.column_stack([np.cos(la) * np.cos(lo),
                                np.cos(la) * np.sin(lo), np.sin(la)])

    tree = cKDTree(xyz(plants.latitude, plants.longitude))
    chord, _ = tree.query(xyz(df.latitude, df.longitude))
    km = 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2, 0, 1))
    near = (km <= PLANT_MATCH_KM).astype(int)

    base = near.mean()
    out = {"model": name, "thermal_plants": int(len(plants)),
           "base_rate": round(float(base), 6)}
    for k in (100, 500, 1000):
        order = np.argsort(scores)[::-1][:k]
        hit = float(near[order].mean())
        out[f"top{k}"] = round(hit, 4)
        out[f"lift{k}"] = round(hit / base, 1) if base else None
    return out


def main():
    df, conflicts = build_labels()
    df = df.reset_index(drop=True)

    is_ihs = df.label_origin == "ihs"
    has_firms = df.firms_label.isin([0, 1])

    print("\n=== Model A: current approach, FIRMS labels only ===")
    oof_a = run(df, "firms_label", has_firms, "A")

    print("\n=== Model B: merged, field verification overrides FIRMS ===")
    oof_b = run(df, "merged_label", pd.Series(True, index=df.index), "B")

    # The yardstick: held-out cells whose label came from people on the ground.
    truth = df.merged_label.values
    results = {"A_firms_only": [], "B_merged": []}
    for name, oof in (("A_firms_only", oof_a), ("B_merged", oof_b)):
        for mask, label in (
            (is_ihs.values, "field-verified IHS cells (the yardstick)"),
            (has_firms.values & ~is_ihs.values, "FIRMS-only cells"),
            (np.ones(len(df), bool), "all labelled cells"),
        ):
            r = score_on(mask, truth, oof, label)
            if r:
                results[name].append(r)

    print("\n" + "=" * 74)
    print("COMPARISON - both models scored on identical held-out cells")
    print("=" * 74)
    for subset in range(len(results["A_firms_only"])):
        a = results["A_firms_only"][subset]
        b = results["B_merged"][subset]
        delta = b["pr_auc"] - a["pr_auc"]
        arrow = "improves" if delta > 0 else "worsens"
        print(f"\n  {a['subset']}   (n={a['n']:,}, {a['positives']:,} positive)")
        print(f"    A  FIRMS labels only : PR-AUC {a['pr_auc']:.4f}  "
              f"ROC {a['roc_auc']:.4f}  p@100 {a['prec_at_100']:.2f}")
        print(f"    B  merged with IHS   : PR-AUC {b['pr_auc']:.4f}  "
              f"ROC {b['roc_auc']:.4f}  p@100 {b['prec_at_100']:.2f}")
        print(f"    -> {arrow} by {abs(delta):.4f} PR-AUC")

    # ---- Hard negatives: the 426 cells people verified as NOT industrial ----
    hard_neg = (df.ihs_label == 0).values
    print("\n" + "=" * 74)
    print("HARD NEGATIVES - cells field-verified as NOT industrial")
    print("=" * 74)
    neg_summary = {}
    for name, oof in (("A_firms_only", oof_a), ("B_merged", oof_b)):
        s_neg = oof[hard_neg]
        flagged = float((s_neg >= 0.9).mean())
        neg_summary[name] = {
            "n": int(hard_neg.sum()),
            "median_score": round(float(np.median(s_neg)), 4),
            "wrongly_scored_above_0.9": int((s_neg >= 0.9).sum()),
            "false_positive_rate": round(flagged, 4),
        }
        print(f"  {name:14s} median score {np.median(s_neg):.3f}   "
              f"wrongly >=0.90: {int((s_neg>=0.9).sum()):>3d} / {int(hard_neg.sum())} "
              f"({flagged:.1%})")

    # ---- Independent WRI check ---------------------------------------------
    print("\n" + "=" * 74)
    print("INDEPENDENT CHECK - WRI thermal plants, never trained on by either")
    print("=" * 74)
    wri = {}
    for name, oof in (("A_firms_only", oof_a), ("B_merged", oof_b)):
        r = wri_check(df, oof, name)
        wri[name] = r
        print(f"  {name:14s} top100 {r['top100']:.3f} ({r['lift100']}x)   "
              f"top500 {r['top500']:.3f} ({r['lift500']}x)   "
              f"top1000 {r['top1000']:.3f} ({r['lift1000']}x)")
    print(f"  (base rate {wri['A_firms_only']['base_rate']:.4%})")

    # ---- Production candidate, trained on everything -----------------------
    y = df.merged_label.values
    weight = (y == 0).sum() / max((y == 1).sum(), 1)
    final = HistGradientBoostingClassifier(**PARAMS)
    final.fit(df[FEATURES], y, sample_weight=np.where(y == 1, weight, 1.0))
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": final, "features": FEATURES,
                 "labels": "FIRMS type-2 with field-verified IHS override",
                 "version": "stage1 / v3 (candidate, not promoted)"}, MODEL_OUT)

    df["score_firms_only"] = oof_a
    df["score_merged"] = oof_b
    df[["cell_id", "latitude", "longitude", "firms_label", "ihs_label",
        "merged_label", "label_origin",
        "score_firms_only", "score_merged"]].to_csv(LABELS_OUT, index=False)

    REPORT_OUT.write_text(json.dumps({
        "purpose": "Ablation: does adding field-verified IHS labels improve stage 1?",
        "promoted": False,
        "production_model_untouched": "models/hotspot_static_source_model.joblib",
        "candidate_model": str(MODEL_OUT),
        "labelled_cells": int(len(df)),
        "from_ihs": int(is_ihs.sum()),
        "from_firms": int((~is_ihs).sum()),
        "conflicting_cells_dropped": conflicts,
        "wri_guard_km": WRI_GUARD_KM,
        "wri_note": "IHS objects near a WRI plant were excluded from training so "
                    "the WRI independent validation stays independent.",
        "results": results,
        "hard_negatives": neg_summary,
        "independent_wri_check": wri,
        "evaluation_caveat": (
            "PR-AUC on the IHS subset is uninformative: that subset is 94.8% "
            "positive because IHS is a catalogue of confirmed sources, not a "
            "balanced sample, so a constant predictor already scores 0.948. "
            "ROC-AUC, the hard negatives and the WRI check are the meaningful reads."
        ),
    }, indent=2), encoding="utf-8")

    print(f"\nCandidate model : {MODEL_OUT}")
    print(f"Comparison      : {REPORT_OUT}")
    print(f"Merged labels   : {LABELS_OUT}")
    print("\nNothing promoted. Production model untouched.")


if __name__ == "__main__":
    main()
