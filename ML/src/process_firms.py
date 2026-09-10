from pathlib import Path

import pandas as pd


# Load the newest downloaded FIRMS file.
raw_dir = Path("data/raw/firms")
latest_file = max(raw_dir.glob("*.csv"), key=lambda file: file.stat().st_mtime)

df = pd.read_csv(latest_file)
raw_count = len(df)

# acq_time may look like 630 instead of 0630.
# zfill(4) converts it into a proper four-digit time.
time_text = df["acq_time"].astype(str).str.zfill(4)

# Combine date and time into one timestamp.
df["detected_at_utc"] = pd.to_datetime(
    df["acq_date"].astype(str) + " " + time_text,
    format="%Y-%m-%d %H%M",
    utc=True,
)

# Keep the columns that matter for our project.
clean_df = df[
    [
        "latitude",
        "longitude",
        "detected_at_utc",
        "satellite",
        "instrument",
        "confidence",
        "bright_ti4",
        "bright_ti5",
        "frp",
        "daynight",
    ]
].copy()

# Remove identical satellite observations, if any.
clean_df = clean_df.drop_duplicates(
    subset=["latitude", "longitude", "detected_at_utc", "satellite"]
)

# Sort events from oldest to newest.
clean_df = clean_df.sort_values("detected_at_utc")

# Save cleaned data separately. Raw NASA data remains unchanged.
output_dir = Path("data/processed")
output_dir.mkdir(parents=True, exist_ok=True)

output_file = output_dir / f"processed_{latest_file.name}"
clean_df.to_csv(output_file, index=False)

print(f"Raw detections: {raw_count}")
print(f"Clean detections: {len(clean_df)}")
print(f"Duplicates removed: {raw_count - len(clean_df)}")
print(f"First detection: {clean_df['detected_at_utc'].min()}")
print(f"Last detection: {clean_df['detected_at_utc'].max()}")
print(f"Saved clean dataset to: {output_file}")