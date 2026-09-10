from pathlib import Path

import numpy as np
import pandas as pd


PREDICTIONS_FILE = Path("data/processed/live_ml_predictions.csv")
HISTORICAL_FILE = Path("data/processed/risk_scored_hotspots_2025.csv")
OUTPUT_FILE = Path("data/processed/live_hybrid_alerts.csv")

GRID_SIZE = 0.05

live_df = pd.read_csv(PREDICTIONS_FILE)

historical_df = pd.read_csv(
    HISTORICAL_FILE,
    usecols=[
        "lat_cell",
        "lon_cell",
        "industrial_thermal_risk_score",
        "risk_level",
        "active_days",
        "total_detections",
    ],
)

live_df["lat_cell"] = np.floor(
    live_df["latitude"] / GRID_SIZE
).astype(int)

live_df["lon_cell"] = np.floor(
    live_df["longitude"] / GRID_SIZE
).astype(int)

alerts_df = live_df.merge(
    historical_df,
    on=["lat_cell", "lon_cell"],
    how="left",
)

alerts_df["historical_risk"] = alerts_df[
    "industrial_thermal_risk_score"
].fillna(0)

alerts_df["historical_match"] = (
    alerts_df["industrial_thermal_risk_score"].notna()
)

# ML provides 65% of the decision; historical persistence provides 35%.
alerts_df["hybrid_alert_score"] = (
    100
    * (
        0.65 * alerts_df["static_source_probability"]
        + 0.35 * (alerts_df["historical_risk"] / 100)
    )
).round(1)

def alert_level(score):
    if score >= 80:
        return "High"
    if score >= 65:
        return "Medium"
    return "Low"

alerts_df["alert_level"] = alerts_df[
    "hybrid_alert_score"
].apply(alert_level)

# Keep only likely static-source predictions.
alerts_df = alerts_df[
    alerts_df["ml_static_candidate"]
].sort_values("hybrid_alert_score", ascending=False)

alerts_df.to_csv(OUTPUT_FILE, index=False)

print(f"ML candidates: {len(alerts_df):,}")
print(
    "Candidates matching historical hotspots: "
    f"{alerts_df['historical_match'].sum():,}"
)

print("\nAlert levels:")
print(alerts_df["alert_level"].value_counts())

print("\nTop hybrid alerts:")
print(
    alerts_df[
        [
            "latitude",
            "longitude",
            "frp",
            "static_source_probability",
            "historical_risk",
            "hybrid_alert_score",
            "alert_level",
        ]
    ].head(20)
)

print(f"\nSaved to: {OUTPUT_FILE}")