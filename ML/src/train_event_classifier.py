"""
Stage 2 of SIH26162: given a thermal place, what KIND of source is it?

Trained ONLY on the GIS-anchored rows from build_event_labels.py - volcanoes
(Smithsonian), thermal power plants (WRI) and mines / refineries / flares /
works (OpenStreetMap). Those labels were produced by people mapping the
ground, not by NASA and not by a rule in this repo, so learning to predict
them from satellite behaviour is a real result rather than a restatement.

The heuristic classes (agricultural burning, wildfire) are deliberately NOT
trained on. A model fed rule-made labels only learns the rule, then reports
its own definition back as accuracy.

Same discipline as the stage-1 model:
  * no latitude / longitude features, so it cannot memorise a world map
  * GroupKFold over 20-degree blocks, so every test region is unseen
  * compared against a majority-class baseline
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupKFold

FEATURES_FILE = Path("data/processed/hotspot_scores_enriched.csv")
LABELS_FILE = Path("data/processed/event_labels_2025.csv")
MODEL_FILE = Path("models/event_classifier.joblib")
METRICS_FILE = Path("models/event_model_metrics.json")
SCORED_FILE = Path("data/processed/event_predictions_2025.csv")

BLOCK_SIZE = 20
N_SPLITS = 5
MIN_CLASS_ROWS = 40      # a class too rare to validate is dropped, not faked

# Only persistent places get an ML type. Below this they are transient fires,
# which the classifier has never seen and must not be asked about.
PERSISTENT_MIN = 0.90
# Measured, not chosen by taste. Out-of-fold precision of the published type
# against the confidence gate:
#     >=0.50  64% coverage  41% correct
#     >=0.70  28% coverage  50% correct
#     >=0.90   8% coverage  68% correct
#     >=0.95   4% coverage  79% correct
# Naming a specific industry below 0.90 would be wrong more often than right,
# so the gate sits there and everything under it falls back to the class the
# features CAN support: industrial, type unspecified.
MIN_CONFIDENCE = 0.90

# Stage 1 already establishes these places are persistent industrial-style
# sources (PR-AUC 0.902). What stage 2 cannot do is say WHICH industry, so
# this is the honest answer for an unmapped place the model is unsure about.
FALLBACK_CLASS = "industrial_unspecified"

ANCHORED_SOURCES = {"osm", "wri_power_plant", "smithsonian_gvp"}

FEATURES = [
    "total_detections", "active_days", "duty_cycle", "span_days",
    "longest_gap_days",
    "months_active", "month_cv", "peak_month_share",
    "night_fraction",
    "frp_mean", "frp_max", "frp_std", "frp_cv",
    "ti4_mean", "ti4_std", "ti5_mean", "ti4_minus_ti5_mean",
    "spread_km", "active_neighbours",
    "static_probability",
]


OUTPUT_COLUMNS = ["event_class", "class_source", "class_confidence"]


def main():
    feats = pd.read_csv(FEATURES_FILE)
    # This script writes its own results back into FEATURES_FILE, so on a
    # second run those columns are already there and would collide with the
    # label file's event_class (giving event_class_x / _y). Drop them first:
    # the label file is the authority for what a place is.
    feats = feats.drop(columns=[c for c in OUTPUT_COLUMNS if c in feats.columns])

    labels = pd.read_csv(
        LABELS_FILE, usecols=["cell_id", "event_class", "label_source"]
    )
    df = feats.merge(labels, on="cell_id", how="inner")

    train = df[df.label_source.isin(ANCHORED_SOURCES)].copy()
    print(f"Anchored rows available: {len(train):,}")

    counts = train.event_class.value_counts()
    keep = counts[counts >= MIN_CLASS_ROWS].index
    dropped = counts[counts < MIN_CLASS_ROWS]
    if len(dropped):
        print(f"\nDropped classes with under {MIN_CLASS_ROWS} rows "
              f"(cannot be validated honestly):")
        print(dropped.to_string())
    train = train[train.event_class.isin(keep)]

    print(f"\nTraining rows: {len(train):,}   classes: {len(keep)}")
    print(train.event_class.value_counts().to_string())

    X = train[FEATURES]
    y = train.event_class.values
    groups = (
        (np.floor(train.latitude / BLOCK_SIZE).astype(int) + 100) * 1000
        + np.floor(train.longitude / BLOCK_SIZE).astype(int)
    )
    print(f"\nSpatial blocks: {groups.nunique()} -> {N_SPLITS}-fold block CV")

    classes = sorted(set(y))
    # Rare classes get weighted up so the model cannot win by always
    # answering with the biggest class.
    freq = pd.Series(y).value_counts()
    weight_for = {c: len(y) / (len(classes) * freq[c]) for c in classes}

    oof = np.empty(len(train), dtype=object)
    fold_f1 = []

    cv = GroupKFold(n_splits=N_SPLITS)
    for fold, (tr, te) in enumerate(cv.split(X, y, groups), start=1):
        model = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
            min_samples_leaf=20, l2_regularization=1.0, random_state=42,
        )
        model.fit(X.iloc[tr], y[tr],
                  sample_weight=np.array([weight_for[v] for v in y[tr]]))
        pred = model.predict(X.iloc[te])
        oof[te] = pred
        score = f1_score(y[te], pred, average="macro", zero_division=0)
        fold_f1.append(score)
        print(f"  fold {fold}: macro-F1 {score:.3f}  ({len(te):,} places)")

    macro = float(np.mean(fold_f1))
    print(f"\n=== Held-out regions: macro-F1 {macro:.3f} "
          f"(+/- {np.std(fold_f1):.3f}) ===\n")

    majority = freq.idxmax()
    base_f1 = f1_score(y, [majority] * len(y), average="macro", zero_division=0)
    print(f"Baseline, always the majority class: macro-F1 {base_f1:.3f}")

    print("\n=== Per-class, out-of-fold ===")
    report = classification_report(y, oof, zero_division=0, output_dict=True)
    print(classification_report(y, oof, zero_division=0))

    matrix = confusion_matrix(y, oof, labels=classes)
    print("Confusion matrix (rows = truth, cols = predicted)")
    print("  " + "  ".join(f"{c[:11]:>11s}" for c in classes))
    for name, row in zip(classes, matrix):
        print(f"{name[:20]:20s} " + "  ".join(f"{v:11d}" for v in row))

    # ---- Production model on every anchored row --------------------------
    production = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
        min_samples_leaf=20, l2_regularization=1.0, random_state=42,
    )
    production.fit(X, y, sample_weight=np.array([weight_for[v] for v in y]))
    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": production, "features": FEATURES,
                 "classes": list(production.classes_)}, MODEL_FILE)

    # ---- Predict a type for EVERY place, anchored or not -----------------
    proba = production.predict_proba(df[FEATURES])
    df["predicted_class"] = production.classes_[proba.argmax(axis=1)]
    df["class_confidence"] = proba.max(axis=1)

    # Start everything as unknown and only overwrite where there is a
    # defensible reason to. Silence is a valid answer for a classifier.
    df["final_class"] = "unknown"
    df["class_source"] = "none"

    # 1. The transient heuristic. The model was never shown a wildfire or a
    #    crop fire, so it cannot speak to them and the rule owns these rows.
    heuristic = df.label_source == "heuristic"
    df.loc[heuristic, "final_class"] = df.loc[heuristic, "event_class"]
    df.loc[heuristic, "class_source"] = "rule"

    # 2. The model's guess, but ONLY for places that are actually persistent
    #    and unmapped. Applying it to transient fires labelled 140,000 crop
    #    fires as power plants: the classifier only knows persistent-source
    #    classes, so asking it about a wildfire guarantees a wrong answer.
    #    A low-confidence guess is also worse than admitting ignorance.
    predictable = (
        (df.static_probability >= PERSISTENT_MIN)
        & (~df.label_source.isin(ANCHORED_SOURCES))
        & (df.class_confidence >= MIN_CONFIDENCE)
    )
    df.loc[predictable, "final_class"] = df.loc[predictable, "predicted_class"]
    df.loc[predictable, "class_source"] = "predicted"

    # Persistent, unmapped, and the model is not confident enough to name a
    # type. Saying "industrial, unspecified" is both true and useful; naming
    # a refinery on a 41%-precision guess is neither.
    unsure = (
        (df.static_probability >= PERSISTENT_MIN)
        & (~df.label_source.isin(ANCHORED_SOURCES))
        & (df.class_confidence < MIN_CONFIDENCE)
    )
    df.loc[unsure, "final_class"] = FALLBACK_CLASS
    df.loc[unsure, "class_source"] = "stage1_only"
    print(f"Persistent but type unresolved:              {int(unsure.sum()):,}")

    # 3. A mapped place always keeps its real label - highest authority, so
    #    it is applied last and overwrites anything above.
    anchored = df.label_source.isin(ANCHORED_SOURCES)
    df.loc[anchored, "final_class"] = df.loc[anchored, "event_class"]
    df.loc[anchored, "class_source"] = "mapped"

    print(f"\nPredicted (persistent, unmapped, confident): "
          f"{int(predictable.sum()):,}")
    print(f"Mapped (external ground truth):              {int(anchored.sum()):,}")
    print(f"Rule (transient heuristic):                  {int(heuristic.sum()):,}")

    # Confidence describes a PREDICTION and nothing else. A mapped power
    # plant is not "99% confident" and a heuristic is not confident at all -
    # leaving the number on those rows invites the dashboard to average them
    # together and report a meaningless figure.
    # Confidence describes a MODEL OUTPUT. A mapped power plant is not "99%
    # confident" and a heuristic is not confident at all, so those are blanked.
    # But a place gated out at stage1_only DID get scored - keeping its number
    # is what lets the dashboard show why the 90% gate sits where it does.
    scored_by_model = df.class_source.isin({"predicted", "stage1_only"})
    df.loc[~scored_by_model, "class_confidence"] = np.nan

    out_cols = ["cell_id", "latitude", "longitude", "static_probability",
                "final_class", "class_source", "class_confidence",
                "predicted_class", "event_class", "label_source"]
    df[out_cols].to_csv(SCORED_FILE, index=False)

    # Write the three classification columns back into the places table the
    # loader uploads, so the API can serve a type per place without a join.
    # Confidence is only meaningful for a prediction - a mapped fact is not
    # 80% true - so it is blanked for everything else.
    enriched = pd.read_csv(FEATURES_FILE)
    enriched = enriched.drop(
        columns=[c for c in OUTPUT_COLUMNS if c in enriched.columns]
    )
    carry = df[["cell_id", "final_class", "class_source", "class_confidence"]].copy()
    carry = carry.rename(columns={"final_class": "event_class"})
    enriched = enriched.merge(carry, on="cell_id", how="left")
    enriched.to_csv(FEATURES_FILE, index=False)
    print(f"Wrote classification columns back into: {FEATURES_FILE}")

    METRICS_FILE.write_text(json.dumps({
        "model_version": "event_classifier / v1",
        "task": "SIH26162 stage 2 - thermal event type classification",
        "trained_on": "GIS-anchored places only (OSM + WRI + Smithsonian GVP)",
        "training_rows": int(len(train)),
        "classes": list(classes),
        "macro_f1": round(macro, 4),
        "macro_f1_std": round(float(np.std(fold_f1)), 4),
        "baseline_macro_f1": round(float(base_f1), 4),
        "folds": [round(f, 4) for f in fold_f1],
        "per_class": {
            c: {k: round(v, 4) for k, v in report[c].items()}
            for c in classes if c in report
        },
        "confusion_matrix": {"labels": list(classes),
                             "rows_are_truth": matrix.tolist()},
        "heuristic_classes": ["agricultural_burning", "wildfire"],
        "heuristic_note": (
            "Separated by a documented rule on FRP, day/night mix and "
            "seasonality, not by the model. No ground truth exists for them "
            "in this dataset, so no accuracy is claimed."
        ),
    }, indent=2), encoding="utf-8")

    print(f"\nSaved model to:       {MODEL_FILE}")
    print(f"Saved metrics to:     {METRICS_FILE}")
    print(f"Saved predictions to: {SCORED_FILE}")
    print("\nFinal class distribution across all places:")
    print(df.final_class.value_counts().to_string())


if __name__ == "__main__":
    main()
