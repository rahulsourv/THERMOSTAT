from pathlib import Path

import joblib
import pandas as pd


RAW_DIR = Path("data/raw/firms")
MODEL_FILE = Path("models/static_source_classifier_2025.joblib")
OUTPUT_FILE = Path("data/processed/live_ml_predictions.csv")

latest_live_file = max(
    RAW_DIR.glob("*.csv"),
    key=lambda file: file.stat().st_mtime,
)

df = pd.read_csv(latest_live_file)

# Create the same features used during training.
time_text = df["acq_time"].astype(str).str.zfill(4)

timestamps = pd.to_datetime(
    df["acq_date"].astype(str) + " " + time_text,
    format="%Y-%m-%d %H%M",
    utc=True,
)

df["month"] = timestamps.dt.month
df["hour_utc"] = timestamps.dt.hour
df["is_night"] = (df["daynight"] == "N").astype(int)

feature_columns = [
    "latitude",
    "longitude",
    "bright_ti4",
    "bright_ti5",
    "frp",
    "confidence",
    "month",
    "hour_utc",
    "is_night",
]

model = joblib.load(MODEL_FILE)

df["static_source_probability"] = model.predict_proba(
    df[feature_columns]
)[:, 1]

# A conservative first threshold.
df["ml_static_candidate"] = (
    df["static_source_probability"] >= 0.70
)

df = df.sort_values(
    "static_source_probability",
    ascending=False,
)

df.to_csv(OUTPUT_FILE, index=False)

candidates = df[df["ml_static_candidate"]]

print(f"Live detections analysed: {len(df):,}")
print(f"ML static-source candidates: {len(candidates):,}")

print("\nTop ML candidates:")
print(
    candidates[
        [
            "latitude",
            "longitude",
            "acq_date",
            "acq_time",
            "frp",
            "confidence",
            "static_source_probability",
        ]
    ].head(20)
)

print(f"\nSaved predictions to: {OUTPUT_FILE}")