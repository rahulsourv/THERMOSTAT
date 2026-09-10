from pathlib import Path

import numpy as np
import pandas as pd


INPUT_FILE = Path("data/processed/static_hotspots_2025.csv")
OUTPUT_FILE = Path("data/processed/hotspot_labeling_sample.csv")

df = pd.read_csv(INPUT_FILE)

# Keep only repeated long-term thermal sources.
candidates = df[df["persistent_candidate"]].copy()

# Divide the world into broad geographic boxes.
# This prevents our sample from coming from only one country.
candidates["lat_region"] = np.floor(candidates["latitude"] / 10).astype(int)
candidates["lon_region"] = np.floor(candidates["longitude"] / 10).astype(int)

candidates = candidates.sort_values(
    ["active_days", "total_detections", "average_frp"],
    ascending=False,
)

# Keep up to three strong candidates from each world region.
sample = (
    candidates.groupby(["lat_region", "lon_region"], group_keys=False)
    .head(3)
    .head(300)
    .copy()
)

sample.insert(
    0,
    "hotspot_id",
    [f"HS2025_{number:04d}" for number in range(1, len(sample) + 1)],
)

# These columns will become our model-training labels.
sample["label"] = ""
sample["label_source"] = ""
sample["review_notes"] = ""

sample.to_csv(OUTPUT_FILE, index=False)

print(f"Persistent candidates available: {len(candidates):,}")
print(f"Labelling sample created: {len(sample):,}")
print(f"Saved to: {OUTPUT_FILE}")