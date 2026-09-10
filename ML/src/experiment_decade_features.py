"""
Would a DECADE of behaviour beat the single year we currently use?

WHY THIS IS NOT SIMPLY "ADD THE COLUMNS"

  The IHS decade profile (date2012_p ... date2021_p) exists for only 1.37% of
  our cells, and that 1.37% is 87.4% positive against 0.099% everywhere else -
  an 880x difference. HistGradientBoosting learns a split direction for NaN,
  so handing it these columns across the full table would teach it exactly one
  thing: "is this cell in the IHS catalogue?" It would post a superb
  cross-validation score and be worthless in production.

  We also cannot build the profile ourselves. Our archive is 2025 only, and
  NOAA-20 did not launch until November 2017, so a decade of NOAA-20 data does
  not exist. The IHS profile came from Suomi-NPP.

WHAT THIS SCRIPT DOES INSTEAD

  Restricts the population to the 8,210 cells that HAVE an IHS label, where
  every row has a decade profile and missingness therefore carries no signal
  at all. Inside that population it asks one question:

      does the decade profile improve industrial vs non-industrial
      discrimination over our current single-year features?

  The answer decides whether it is worth requesting a multi-year Suomi-NPP
  archive from FIRMS - which is a large download and days of processing, so
  it deserves evidence first.

  ROC-AUC is the headline, not PR-AUC: this subset is 94.8% positive, where a
  constant predictor already scores 0.948 on PR-AUC.

Promotes nothing. Writes one JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold

FEATURES_FILE = Path("data/processed/hotspot_features_2025.csv")
LABELS_FILE = Path("data/processed/stage1_merged_labels.csv")
IHS_FILE = Path("data/processed/ihs_points.csv")
REPORT_OUT = Path("models/decade_feature_experiment.json")

BLOCK_SIZE = 20
N_SPLITS = 5
CELL_MATCH_KM = 4.0

BASE_FEATURES = [
    "total_detections", "active_days", "duty_cycle", "span_days",
    "longest_gap_days",
    "months_active", "month_cv", "peak_month_share",
    "night_fraction",
    "frp_mean", "frp_max", "frp_std", "frp_cv",
    "ti4_mean", "ti4_std", "ti5_mean", "ti4_minus_ti5_mean",
    "spread_km", "active_neighbours",
]

YEAR_COLS = [f"date{y}_p" for y in range(2012, 2022)]

PARAMS = dict(max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
              min_samples_leaf=20, l2_regularization=1.0, random_state=42)


def decade_features(g: pd.DataFrame) -> pd.DataFrame:
    """Per-cell summary of ten years of activity.

    Raw yearly counts are included, but the derived columns are the ones with
    a physical story: a kiln burns EVERY year, a recurring crop fire does not.
    """
    counts = g[YEAR_COLS].to_numpy(float)
    years = np.arange(2012, 2022)

    active = counts > 0
    total = counts.sum(axis=1)
    mean = counts.mean(axis=1)
    std = counts.std(axis=1)

    # Linear trend, normalised by level so a big site and a small site with
    # the same shape look the same.
    centred = years - years.mean()
    slope = (counts * centred).sum(axis=1) / (centred ** 2).sum()

    def longest_gap(row):
        gap = best = 0
        for on in row:
            gap = 0 if on else gap + 1
            best = max(best, gap)
        return best

    out = pd.DataFrame(counts, columns=YEAR_COLS, index=g.index)
    out["decade_total"] = total
    out["decade_years_active"] = active.sum(axis=1)
    out["decade_cv"] = np.divide(std, mean, out=np.zeros_like(std),
                                 where=mean > 0)
    out["decade_trend"] = np.divide(slope, mean, out=np.zeros_like(slope),
                                    where=mean > 0)
    out["decade_first_year"] = np.where(
        active.any(axis=1), years[active.argmax(axis=1)], 0)
    out["decade_last_year"] = np.where(
        active.any(axis=1), years[active.shape[1] - 1 - active[:, ::-1].argmax(axis=1)], 0)
    out["decade_longest_gap"] = [longest_gap(r) for r in active]
    return out


def evaluate(X, y, groups, label):
    oof = np.zeros(len(X))
    for tr, te in GroupKFold(n_splits=N_SPLITS).split(X, y, groups):
        if len(np.unique(y[tr])) < 2:
            continue
        w = (y[tr] == 0).sum() / max((y[tr] == 1).sum(), 1)
        m = HistGradientBoostingClassifier(**PARAMS)
        m.fit(X.iloc[tr], y[tr], sample_weight=np.where(y[tr] == 1, w, 1.0))
        oof[te] = m.predict_proba(X.iloc[te])[:, 1]

    roc = float(roc_auc_score(y, oof))
    pr = float(average_precision_score(y, oof))
    # Recall on the verified positives at a fixed 10% false-positive rate on
    # the verified negatives - the like-for-like read from step 1.
    neg, pos = oof[y == 0], oof[y == 1]
    thresh = float(np.quantile(neg, 0.90))
    recall_at_10fp = float((pos >= thresh).mean())
    print(f"  {label:38s} ROC-AUC {roc:.4f}   PR-AUC {pr:.4f}   "
          f"recall@10%FP {recall_at_10fp:.1%}")
    return {"features": label, "n_features": X.shape[1],
            "roc_auc": round(roc, 4), "pr_auc": round(pr, 4),
            "recall_at_10pct_fp": round(recall_at_10fp, 4)}, oof


def main():
    feats = pd.read_csv(FEATURES_FILE)
    labels = pd.read_csv(LABELS_FILE, usecols=["cell_id", "ihs_label"])
    ihs = pd.read_csv(IHS_FILE)

    # One IHS object per cell: the closest, so the decade profile belongs to
    # the object actually sitting on that cell.
    near = ihs[ihs.km_to_our_place <= CELL_MATCH_KM].sort_values("km_to_our_place")
    near = near.drop_duplicates(subset="our_cell_id", keep="first")

    df = (feats
          .merge(labels[labels.ihs_label.notna()], on="cell_id", how="inner")
          .merge(near[["our_cell_id"] + YEAR_COLS],
                 left_on="cell_id", right_on="our_cell_id", how="inner"))
    df = df.dropna(subset=YEAR_COLS).reset_index(drop=True)

    y = df.ihs_label.astype(int).to_numpy()
    print(f"Population: {len(df):,} field-verified cells "
          f"({int(y.sum()):,} industrial / {int((1-y).sum()):,} not)")
    print("Every row has a decade profile, so missingness carries no signal.\n")

    groups = (
        (np.floor(df.latitude / BLOCK_SIZE).astype(int) + 100) * 1000
        + np.floor(df.longitude / BLOCK_SIZE).astype(int)
    )
    print(f"Spatial blocks: {groups.nunique()}  ->  {N_SPLITS}-fold block CV\n")

    dec = decade_features(df)
    derived = [c for c in dec.columns if c.startswith("decade_")]

    print("=== Does a decade of behaviour beat one year? ===")
    results = []
    r, _ = evaluate(df[BASE_FEATURES], y, groups,
                    "A. 2025 only (what we use today)")
    results.append(r)
    r, _ = evaluate(pd.concat([df[BASE_FEATURES], dec[derived]], axis=1), y,
                    groups, "B. 2025 + decade summary")
    results.append(r)
    r, _ = evaluate(pd.concat([df[BASE_FEATURES], dec], axis=1), y, groups,
                    "C. 2025 + decade summary + raw years")
    results.append(r)
    r, _ = evaluate(dec, y, groups, "D. decade ONLY (no 2025 features)")
    results.append(r)

    base = results[0]["roc_auc"]
    best = max(results[1:], key=lambda r: r["roc_auc"])
    gain = best["roc_auc"] - base
    print(f"\nBest decade variant: {best['features']}")
    print(f"  ROC-AUC {base:.4f} -> {best['roc_auc']:.4f}  (gain {gain:+.4f})")

    worth_it = gain >= 0.02
    verdict = (
        "WORTH IT - request a multi-year Suomi-NPP archive from FIRMS and "
        "rebuild these features for all 687,289 cells."
        if worth_it else
        "NOT WORTH IT - the decade profile adds too little to justify "
        "downloading and reprocessing a decade of Suomi-NPP data."
    )
    print(f"\nVerdict: {verdict}")

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(json.dumps({
        "question": "Does a 10-year persistence profile beat our single 2025 year?",
        "why_restricted": (
            "The decade profile exists for only 1.37% of our cells and that "
            "subset is 87.4% positive vs 0.099% elsewhere. Adding these columns "
            "to the full table would let the model read the label off feature "
            "missingness. This experiment therefore runs only where every row "
            "has the profile."
        ),
        "cannot_self_compute": (
            "Our FIRMS archive is 2025 only, and NOAA-20 launched in November "
            "2017, so a decade of NOAA-20 data does not exist. The IHS profile "
            "came from Suomi-NPP."
        ),
        "population": {"cells": int(len(df)), "positive": int(y.sum()),
                       "negative": int((1 - y).sum())},
        "headline_metric": "ROC-AUC (subset is 94.8% positive, so PR-AUC is uninformative)",
        "results": results,
        "gain_over_baseline": round(gain, 4),
        "verdict": verdict,
        "promoted": False,
    }, indent=2), encoding="utf-8")
    print(f"\nSaved: {REPORT_OUT}")


if __name__ == "__main__":
    main()
