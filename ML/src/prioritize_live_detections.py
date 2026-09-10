from pathlib import Path

import numpy as np
import pandas as pd


RAW_DIR = Path("data/raw/firms")
HOTSPOT_FILE = Path("data/processed/risk_scored_hotspots_2025.csv")
OUTPUT_DIR = Path("data/processed")

# Load the newest live FIRMS download.
latest_live_file = max(
    RAW_DIR.glob("*.csv"),
    key=lambda file: file.stat().st_mtime,
)

live_df = pd.read_csv(latest_live_file)

# Load historical risk hotspots.
hotspots_df = pd.read_csv(
    HOTSPOT_FILE,
    usecols=[
        "lat_cell",
        "lon_cell",
        "industrial_thermal_risk_score",
        "risk_level",
        "active_days",
        "total_detections",
    ],
)

# Use the same 5 km grid used in historical hotspot analysis.
GRID_SIZE = 0.05

live_df["lat_cell"] = np.floor(
    live_df["latitude"] / GRID_SIZE
).astype(int)

live_df["lon_cell"] = np.floor(
    live_df["longitude"] / GRID_SIZE
).astype(int)

# Match each new detection with any historical hotspot in its grid cell.
prioritized_df = live_df.merge(
    hotspots_df,
    on=["lat_cell", "lon_cell"],
    how="left",
)

# Keep only detections near historical static thermal hotspots.
prioritized_df = prioritized_df.dropna(
    subset=["industrial_thermal_risk_score"]
)

prioritized_df = prioritized_df.sort_values(
    "industrial_thermal_risk_score",
    ascending=False,
)

output_file = OUTPUT_DIR / "live_prioritized_detections.csv"
prioritized_df.to_csv(output_file, index=False)

print(f"Newest live file: {latest_live_file.name}")
print(f"All new detections: {len(live_df):,}")
print(
    "Detections near historical thermal hotspots: "
    f"{len(prioritized_df):,}"
)

print("\nHigh-risk detections:")
print(
    prioritized_df[
        [
            "latitude",
            "longitude",
            "frp",
            "confidence",
            "industrial_thermal_risk_score",
            "risk_level",
            "active_days",
        ]
    ].head(20)
)

print(f"\nSaved to: {output_file}")