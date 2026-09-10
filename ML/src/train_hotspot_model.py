"""
Train the PLACE-level static-thermal-source model.

Three things this does differently from the old detection-level model:

 1. No latitude / longitude / hour features.
    Latitude alone scored AUC 0.922 on the old data, which means the old
    model was mostly memorising a world map of oil fields.

 2. Spatial block validation instead of a random split.
    The world is cut into 20-degree blocks. Whole blocks are held out, so
    the model is always tested on regions it has never seen. A random
    split lets the same flare appear in both train and test.

 3. It is compared against simple baselines. If a hand-written rule wins,
    the machine learning is not earning its place.

Headline metric is Average Precision (PR-AUC), not ROC-AUC, because only
about 0.6% of places are static sources and ROC-AUC flatters rare classes.
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold

INPUT_FILE = Path("data/processed/hotspot_features_2025.csv")
MODEL_FILE = Path("models/hotspot_static_source_model.joblib")
SCORED_FILE = Path("data/processed/hotspot_model_scores_2025.csv")

BLOCK_SIZE = 20      # degrees, for the spatial hold-out blocks
N_SPLITS = 5

# Deliberately NO latitude, longitude, first_doy, last_doy or hour.
FEATURES = [
    # persistence
    "total_detections", "active_days", "duty_cycle", "span_days",
    "longest_gap_days",
    # seasonality
    "months_active", "month_cv", "peak_month_share",
    # day / night
    "night_fraction",
    # thermal character
    "frp_mean", "frp_max", "frp_std", "frp_cv",
    "ti4_mean", "ti4_std", "ti5_mean", "ti4_minus_ti5_mean",
    # spatial character
    "spread_km", "active_neighbours",
]

df = pd.read_csv(INPUT_FILE)
df = df[df["label"] >= 0].copy()          # drop the mixed "unknown" cells

X = df[FEATURES]
y = df["label"].astype(int)

# Spatial blocks: whole 20-degree squares are held out together.
groups = (
    (np.floor(df["latitude"] / BLOCK_SIZE).astype(int) + 100) * 1000
    + np.floor(df["longitude"] / BLOCK_SIZE).astype(int)
)

print(f"Places: {len(df):,}")
print(f"  static-like (1):     {int((y == 1).sum()):,}")
print(f"  vegetation-like (0): {int((y == 0).sum()):,}")
print(f"  positive rate: {y.mean():.3%}")
print(f"Spatial blocks: {groups.nunique()}  ->  {N_SPLITS}-fold block CV\n")


def precision_at_k(y_true, scores, k=100):
    """Of our top k alerts, what share are really static sources?"""
    order = np.argsort(scores)[::-1][:k]
    return float(np.asarray(y_true)[order].mean())


# --------------------------------------------------------------------------
# Cross-validation across held-out regions
# --------------------------------------------------------------------------
cv = GroupKFold(n_splits=N_SPLITS)
rows = []
oof_scores = np.zeros(len(df))

for fold, (train_idx, test_idx) in enumerate(cv.split(X, y, groups), start=1):
    X_tr, X_te = X.iloc[train_idx], X.iloc[test_idx]
    y_tr, y_te = y.iloc[train_idx], y.iloc[test_idx]

    # Rare positives: weight them up so the model cannot win by
    # always answering "vegetation fire".
    pos_weight = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)
    weights = np.where(y_tr == 1, pos_weight, 1.0)

    model = HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.06,
        max_leaf_nodes=31,
        min_samples_leaf=40,
        l2_regularization=1.0,
        random_state=42,
    )
    model.fit(X_tr, y_tr, sample_weight=weights)

    scores = model.predict_proba(X_te)[:, 1]
    oof_scores[test_idx] = scores

    rows.append({
        "fold": fold,
        "test_places": len(y_te),
        "test_positives": int(y_te.sum()),
        "PR_AUC": average_precision_score(y_te, scores),
        "ROC_AUC": roc_auc_score(y_te, scores),
        "prec@100": precision_at_k(y_te, scores, 100),
    })
    print(
        f"fold {fold}: "
        f"PR-AUC {rows[-1]['PR_AUC']:.3f}  "
        f"ROC-AUC {rows[-1]['ROC_AUC']:.3f}  "
        f"prec@100 {rows[-1]['prec@100']:.2f}  "
        f"({int(y_te.sum())} positives in {len(y_te):,} places)"
    )

results = pd.DataFrame(rows)
print("\n=== Model, averaged over held-out regions ===")
for metric in ["PR_AUC", "ROC_AUC", "prec@100"]:
    print(
        f"  {metric:9s} {results[metric].mean():.3f} "
        f"(+/- {results[metric].std():.3f})"
    )

# --------------------------------------------------------------------------
# Baselines: simple rules the model has to beat
# --------------------------------------------------------------------------
print("\n=== Baselines (same held-out data, no learning) ===")


def rank_score(series):
    return series.rank(pct=True).values


baselines = {
    "active_days alone": rank_score(df["active_days"]),
    "night_fraction alone": rank_score(df["night_fraction"]),
    "duty_cycle alone": rank_score(df["duty_cycle"]),
    # the hand-written formula from score_hotspots.py
    "your risk formula": (
        0.40 * (df["active_days"] / df["active_days"].max()).values
        + 0.25 * rank_score(df["total_detections"])
        + 0.20 * rank_score(df["frp_mean"])
        + 0.15 * df["night_fraction"].values
    ),
}

summary = [{
    "approach": "ML model (block CV)",
    "PR_AUC": results["PR_AUC"].mean(),
    "ROC_AUC": results["ROC_AUC"].mean(),
    "prec@100": results["prec@100"].mean(),
}]
for name, score in baselines.items():
    summary.append({
        "approach": name,
        "PR_AUC": average_precision_score(y, score),
        "ROC_AUC": roc_auc_score(y, score),
        "prec@100": precision_at_k(y, score, 100),
    })
    print(
        f"  {name:22s} PR-AUC {summary[-1]['PR_AUC']:.3f}  "
        f"ROC-AUC {summary[-1]['ROC_AUC']:.3f}  "
        f"prec@100 {summary[-1]['prec@100']:.2f}"
    )

print("\n=== Comparison ===")
print(pd.DataFrame(summary).round(3).to_string(index=False))

# --------------------------------------------------------------------------
# Which clues actually mattered
# --------------------------------------------------------------------------
print("\n=== Feature importance (permutation, held-out fold) ===")
train_idx, test_idx = next(iter(cv.split(X, y, groups)))
pos_weight = (y.iloc[train_idx] == 0).sum() / max((y.iloc[train_idx] == 1).sum(), 1)
final_model = HistGradientBoostingClassifier(
    max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
    min_samples_leaf=40, l2_regularization=1.0, random_state=42,
)
final_model.fit(
    X.iloc[train_idx], y.iloc[train_idx],
    sample_weight=np.where(y.iloc[train_idx] == 1, pos_weight, 1.0),
)
imp = permutation_importance(
    final_model, X.iloc[test_idx], y.iloc[test_idx],
    scoring="average_precision", n_repeats=3, random_state=42, n_jobs=1,
)
for name, value in sorted(
    zip(FEATURES, imp.importances_mean), key=lambda p: -p[1]
):
    bar = "#" * max(int(value * 300), 0)
    print(f"  {name:22s} {value:+.4f}  {bar}")

# --------------------------------------------------------------------------
# Final model on all data + scored output
# --------------------------------------------------------------------------
pos_weight = (y == 0).sum() / max((y == 1).sum(), 1)
production = HistGradientBoostingClassifier(
    max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
    min_samples_leaf=40, l2_regularization=1.0, random_state=42,
)
production.fit(X, y, sample_weight=np.where(y == 1, pos_weight, 1.0))

MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
joblib.dump({"model": production, "features": FEATURES}, MODEL_FILE)

# Out-of-fold scores are the honest ones: every place was scored by a
# model that never saw its region.
df["static_probability"] = oof_scores
df.sort_values("static_probability", ascending=False).to_csv(
    SCORED_FILE, index=False
)

print(f"\nSaved model to:  {MODEL_FILE}")
print(f"Saved scores to: {SCORED_FILE}")
