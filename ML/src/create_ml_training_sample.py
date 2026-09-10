from pathlib import Path

import pandas as pd


INPUT_FILE = Path("data/processed/archive_2025_noaa20_clean.csv")
OUTPUT_FILE = Path("data/processed/ml_training_sample_2025.csv")

CHUNK_SIZE = 200_000
SAMPLES_PER_CLASS_PER_CHUNK = 2_000

total_positive = 0
total_negative = 0

for chunk_number, chunk in enumerate(
    pd.read_csv(INPUT_FILE, chunksize=CHUNK_SIZE),
    start=1,
):
    chunk["fire_type"] = pd.to_numeric(
        chunk["fire_type"],
        errors="coerce",
    )

    # 1 = static-source candidate, 0 = presumed vegetation-fire example.
    positive = chunk[chunk["fire_type"] == 2].copy()
    negative = chunk[chunk["fire_type"] == 0].copy()

    positive = positive.sample(
        n=min(SAMPLES_PER_CLASS_PER_CHUNK, len(positive)),
        random_state=chunk_number,
    )

    negative = negative.sample(
        n=min(SAMPLES_PER_CLASS_PER_CHUNK, len(negative)),
        random_state=chunk_number,
    )

    sample = pd.concat([positive, negative], ignore_index=True)

    if sample.empty:
        continue

    timestamp = pd.to_datetime(
        sample["detected_at_utc"],
        utc=True,
    )

    sample["month"] = timestamp.dt.month
    sample["hour_utc"] = timestamp.dt.hour
    sample["is_night"] = (sample["daynight"] == "N").astype(int)

    sample["static_source_label"] = (
        sample["fire_type"] == 2
    ).astype(int)

    training_columns = [
        "latitude",
        "longitude",
        "bright_ti4",
        "bright_ti5",
        "frp",
        "confidence",
        "month",
        "hour_utc",
        "is_night",
        "static_source_label",
    ]

    sample = sample[training_columns]

    mode = "w" if chunk_number == 1 else "a"

    sample.to_csv(
        OUTPUT_FILE,
        mode=mode,
        header=(chunk_number == 1),
        index=False,
    )

    total_positive += (sample["static_source_label"] == 1).sum()
    total_negative += (sample["static_source_label"] == 0).sum()

    print(
        f"Chunk {chunk_number}: "
        f"{total_positive:,} static-source examples, "
        f"{total_negative:,} vegetation-fire examples"
    )

print("\nTraining sample complete.")
print(f"Static-source examples: {total_positive:,}")
print(f"Vegetation-fire examples: {total_negative:,}")
print(f"Saved to: {OUTPUT_FILE}")