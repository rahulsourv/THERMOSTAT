from pathlib import Path

import numpy as np
import pandas as pd


INPUT_FILE = Path("data/processed/static_source_candidates_2025.csv")
OUTPUT_FILE = Path("data/processed/static_hotspots_2025.csv")

# Read only columns needed for hotspot analysis.
df = pd.read_csv(
    INPUT_FILE,
    usecols=[
        "latitude",
        "longitude",
        "detected_at_utc",
        "bright_ti4",
        "frp",
        "daynight",
    ],
)

df["detected_at_utc"] = pd.to_datetime(df["detected_at_utc"], utc=True)
df["event_date"] = df["detected_at_utc"].dt.strftime("%Y-%m-%d")

# Each cell is approximately 5 km × 5 km.
GRID_SIZE = 0.05

df["lat_cell"] = np.floor(df["latitude"] / GRID_SIZE).astype(int)
df["lon_cell"] = np.floor(df["longitude"] / GRID_SIZE).astype(int)
df["is_night"] = (df["daynight"] == "N").astype(int)

hotspots = (
    df.groupby(["lat_cell", "lon_cell"])
    .agg(
        latitude=("latitude", "mean"),
        longitude=("longitude", "mean"),
        total_detections=("frp", "size"),
        active_days=("event_date", "nunique"),
        average_frp=("frp", "mean"),
        maximum_frp=("frp", "max"),
        average_temperature=("bright_ti4", "mean"),
        nighttime_detections=("is_night", "sum"),
        first_seen=("detected_at_utc", "min"),
        last_seen=("detected_at_utc", "max"),
    )
    .reset_index()
)

hotspots["nighttime_ratio"] = (
    hotspots["nighttime_detections"] / hotspots["total_detections"]
)

# 12+ active days is our first persistence screen.
# It is a candidate rule, not an industrial-fire label.
hotspots["persistent_candidate"] = hotspots["active_days"] >= 12

hotspots = hotspots.sort_values(
    ["active_days", "total_detections", "average_frp"],
    ascending=False,
)

hotspots.to_csv(OUTPUT_FILE, index=False)

print(f"Candidate detections analysed: {len(df):,}")
print(f"Unique hotspots found: {len(hotspots):,}")
print(
    "Persistent candidates "
    f"(active on 12+ days): {hotspots['persistent_candidate'].sum():,}"
)

print("\nTop 15 persistent hotspots:")
print(
    hotspots[
        [
            "latitude",
            "longitude",
            "total_detections",
            "active_days",
            "average_frp",
            "nighttime_ratio",
            "persistent_candidate",
        ]
    ].head(15)
)

print(f"\nSaved hotspot dataset to: {OUTPUT_FILE}")