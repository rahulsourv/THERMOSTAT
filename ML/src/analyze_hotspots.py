from pathlib import Path
import pandas as pd

data_dir = Path("data/raw/firms")
latest_file = max(data_dir.glob("*.csv"), key=lambda file: file.stat().st_mtime)

df = pd.read_csv(latest_file)

print(f"Dataset: {latest_file.name}")
print(f"Total detections: {len(df)}")

print("\nDetections per date:")
print(df["acq_date"].value_counts().sort_index())

print("\nConfidence levels:")
print(df["confidence"].value_counts())

print("\nDay or night detections:")
print(df["daynight"].value_counts())

print("\nThermal summary:")
print(df[["bright_ti4", "bright_ti5", "frp"]].describe())

df["lat_grid"] = df["latitude"].round(2)
df["lon_grid"] = df["longitude"].round(2)

hotspots = (
    df.groupby(["lat_grid", "lon_grid"])
    .agg(
        detections=("frp", "size"),
        average_frp=("frp", "mean"),
        average_temperature=("bright_ti4", "mean"),
    )
    .sort_values("detections", ascending=False)
    .head(15)
)

print("\nTop 15 repeated hotspots:")
print(hotspots)