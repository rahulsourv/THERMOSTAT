from collections import Counter
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


ARCHIVE_DIR = Path("data/external/firms_archives")
OUTPUT_FILE = Path("data/processed/archive_2025_noaa20_clean.csv")
CHUNK_SIZE = 200_000

zip_files = list(ARCHIVE_DIR.glob("*.zip"))

if not zip_files:
    raise FileNotFoundError("No archive ZIP found.")

archive_file = max(zip_files, key=lambda file: file.stat().st_mtime)

with ZipFile(archive_file) as archive:
    csv_files = [
        info.filename
        for info in archive.infolist()
        if info.filename.lower().endswith(".csv")
    ]

    if not csv_files:
        raise FileNotFoundError("No CSV found inside the ZIP.")

    csv_file = csv_files[0]

    print(f"Processing: {archive_file.name}")
    print(f"Reading inside ZIP: {csv_file}")

    total_rows = 0
    invalid_times = 0
    type_counts = Counter()

    # The CSV is read 200,000 rows at a time, not all at once.
    with archive.open(csv_file) as file:
        reader = pd.read_csv(file, chunksize=CHUNK_SIZE)

        for chunk_number, chunk in enumerate(reader, start=1):
            total_rows += len(chunk)

            # Make archive field names match our live FIRMS field names.
            chunk = chunk.rename(
                columns={
                    "brightness": "bright_ti4",
                    "bright_t31": "bright_ti5",
                    "type": "fire_type",
                }
            )

            # Build one proper timestamp from date and time.
            time_text = chunk["acq_time"].astype(str).str.zfill(4)

            chunk["detected_at_utc"] = pd.to_datetime(
                chunk["acq_date"].astype(str) + " " + time_text,
                format="%Y-%m-%d %H%M",
                utc=True,
                errors="coerce",
            )

            invalid_times += chunk["detected_at_utc"].isna().sum()

            # Count NASA fire-type values for later analysis.
            type_counts.update(chunk["fire_type"].value_counts().to_dict())

            clean_chunk = chunk[
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
                    "fire_type",
                ]
            ].dropna(subset=["detected_at_utc"])

            # First chunk creates the file; later chunks add to it.
            mode = "w" if chunk_number == 1 else "a"
            clean_chunk.to_csv(
                OUTPUT_FILE,
                mode=mode,
                header=(chunk_number == 1),
                index=False,
            )

            print(
                f"Chunk {chunk_number}: "
                f"{total_rows:,} source rows processed"
            )

print("\nProcessing complete.")
print(f"Total archive rows processed: {total_rows:,}")
print(f"Rows with invalid timestamps removed: {invalid_times:,}")
print("Fire-type counts:")
print(dict(type_counts))
print(f"\nClean output saved to: {OUTPUT_FILE}")