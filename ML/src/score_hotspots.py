from pathlib import Path

import pandas as pd


INPUT_FILE = Path("data/processed/static_hotspots_2025.csv")
OUTPUT_FILE = Path("data/processed/risk_scored_hotspots_2025.csv")

df = pd.read_csv(INPUT_FILE)

# Convert each feature to a 0–1 relative score.
df["persistence_score"] = df["active_days"] / df["active_days"].max()

df["detection_score"] = df["total_detections"].rank(
    pct=True
)

df["intensity_score"] = df["average_frp"].rank(
    pct=True
)

df["nighttime_score"] = df["nighttime_ratio"]

# Weighted first-version industrial thermal risk score.
df["industrial_thermal_risk_score"] = (
    100
    * (
        0.40 * df["persistence_score"]
        + 0.25 * df["detection_score"]
        + 0.20 * df["intensity_score"]
        + 0.15 * df["nighttime_score"]
    )
).round(1)

def risk_level(score):
    if score >= 75:
        return "High"
    if score >= 50:
        return "Medium"
    return "Low"

df["risk_level"] = df["industrial_thermal_risk_score"].apply(risk_level)

df = df.sort_values(
    "industrial_thermal_risk_score",
    ascending=False,
)

df.to_csv(OUTPUT_FILE, index=False)

print("Risk-scored hotspots:")
print(df[[
    "latitude",
    "longitude",
    "active_days",
    "total_detections",
    "average_frp",
    "nighttime_ratio",
    "industrial_thermal_risk_score",
    "risk_level",
]].head(20))

print(f"\nSaved to: {OUTPUT_FILE}")