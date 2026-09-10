from pathlib import Path

import pandas as pd


processed_dir = Path("data/processed")

# Read every clean FIRMS dataset in the processed folder.
files = list(processed_dir.glob("processed_*.csv"))

if not files:
    raise FileNotFoundError("No processed FIRMS files found.")

dataframes = []

for file in files:
    df = pd.read_csv(file)
    df["detected_at_utc"] = pd.to_datetime(
        df["detected_at_utc"],
        utc=True,
    )
    dataframes.append(df)

# Join all clean files into one history dataset.
history_df = pd.concat(dataframes, ignore_index=True)

# Remove duplicate events that may appear if the same day is downloaded twice.
history_df = history_df.drop_duplicates(
    subset=["latitude", "longitude", "detected_at_utc", "satellite"]
)

history_df = history_df.sort_values("detected_at_utc")

output_file = processed_dir / "global_firms_history.csv"
history_df.to_csv(output_file, index=False)

print(f"Processed files combined: {len(files)}")
print(f"Total unique events: {len(history_df)}")
print(f"History starts: {history_df['detected_at_utc'].min()}")
print(f"History ends: {history_df['detected_at_utc'].max()}")
print(f"Saved history to: {output_file}")