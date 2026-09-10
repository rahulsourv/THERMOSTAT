from pathlib import Path

import pandas as pd


history_file = Path("data/processed/global_firms_history.csv")
df = pd.read_csv(history_file)

df["detected_at_utc"] = pd.to_datetime(df["detected_at_utc"], utc=True)
df["event_date"] = df["detected_at_utc"].dt.date

# A 0.05-degree grid is roughly a 5 km area.
# Nearby detections inside the same cell become one hotspot.
grid_size = 0.05

df["lat_cell"] = (df["latitude"] / grid_size).round().astype(int)
df["lon_cell"] = (df["longitude"] / grid_size).round().astype(int)

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
        first_seen=("detected_at_utc", "min"),
        last_seen=("detected_at_utc", "max"),
    )
    .reset_index()
)

# A simple first signal of whether a location may be persistent.
hotspots["persistent_candidate"] = hotspots["active_days"] >= 2

hotspots = hotspots.sort_values(
    ["active_days", "total_detections", "average_frp"],
    ascending=False,
)

output_file = Path("data/processed/hotspots.csv")
hotspots.to_csv(output_file, index=False)

print(f"Unique hotspots found: {len(hotspots)}")
print(f"Persistent candidates: {hotspots['persistent_candidate'].sum()}")

print("\nTop 15 hotspots:")
print(
    hotspots[
        [
            "latitude",
            "longitude",
            "total_detections",
            "active_days",
            "average_frp",
            "maximum_frp",
            "persistent_candidate",
        ]
    ].head(15)
)

print(f"\nSaved hotspots to: {output_file}")