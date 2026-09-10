from pathlib import Path

import pandas as pd


INPUT_FILE = Path("data/processed/archive_2025_noaa20_clean.csv")
OUTPUT_FILE = Path("data/processed/static_source_candidates_2025.csv")
CHUNK_SIZE = 200_000

total_candidates = 0

for chunk_number, chunk in enumerate(
    pd.read_csv(INPUT_FILE, chunksize=CHUNK_SIZE),
    start=1,
):
    chunk["fire_type"] = pd.to_numeric(chunk["fire_type"], errors="coerce")

    # Type 2 = possible static thermal source.
    candidates = chunk[chunk["fire_type"] == 2]

    total_candidates += len(candidates)

    mode = "w" if chunk_number == 1 else "a"

    candidates.to_csv(
        OUTPUT_FILE,
        mode=mode,
        header=(chunk_number == 1),
        index=False,
    )

    print(
        f"Chunk {chunk_number}: "
        f"{total_candidates:,} static-source candidates found so far"
    )

print("\nFinished.")
print(f"Total candidates saved: {total_candidates:,}")
print(f"Saved to: {OUTPUT_FILE}")