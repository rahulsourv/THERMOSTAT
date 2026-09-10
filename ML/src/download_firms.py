"""Download recent NASA FIRMS thermal-anomaly detections (worldwide).

Safe to run unattended: it always asks for the NEWEST data, retries if the
network hiccups, and refuses to overwrite good data with an empty response.
"""

import os
import sys
import time
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# Works no matter which folder the script is launched from.
ML_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ML_ROOT / ".env")

MAP_KEY = os.getenv("FIRMS_MAP_KEY")
if not MAP_KEY:
    raise ValueError("FIRMS_MAP_KEY not found in ML/.env")

AREA = "world"
PRODUCT = "VIIRS_NOAA20_NRT"

# 2, not 1, and the reason matters.
#
# FIRMS counts days as UTC CALENDAR days, not the last 24 hours. A run at
# 01:30 UTC therefore sees a 90-minute-old day: the 07:00 IST scheduled run
# on 2026-09-07 returned 3,059 detections where the previous evening's run
# returned 40,602.
#
# It also loses India entirely at night. NOAA-20 crosses India at ~01:30
# local, which is ~20:00 UTC the PREVIOUS calendar day, so a single-day
# window systematically drops the night pass - and India's industrial
# sources are 90-100% night-detected.
#
# Two days always contains one complete UTC day plus whatever has accrued
# today, so the dashboard can never be starved by the clock.
DAYS = 2

# START_DATE must stay empty for automation. If you pin a date here, every
# scheduled run re-downloads that same day forever and the data never moves.
# Set it only for a one-off backfill of a specific past date.
START_DATE = ""

MAX_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 30
MIN_EXPECTED_ROWS = 100     # a real world-wide day has tens of thousands


def build_url() -> str:
    url = (
        f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        f"{MAP_KEY}/{PRODUCT}/{AREA}/{DAYS}"
    )
    return f"{url}/{START_DATE}" if START_DATE else url


def fetch() -> pd.DataFrame:
    """Ask FIRMS for data, retrying on temporary failures."""
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            print(f"Requesting FIRMS data (attempt {attempt}/{MAX_ATTEMPTS})...")
            response = requests.get(build_url(), timeout=120)

            if response.status_code == 200:
                text = response.text
                # FIRMS returns HTTP 200 with a plain-text error for a bad key
                # or a rate limit, so check the body actually looks like CSV.
                if not text.lstrip().lower().startswith("latitude"):
                    raise RuntimeError(f"Unexpected response: {text[:200]}")
                return pd.read_csv(StringIO(text))

            # 4xx will not fix itself; stop straight away.
            if 400 <= response.status_code < 500:
                raise RuntimeError(
                    f"FIRMS rejected the request: {response.status_code}\n"
                    f"{response.text[:300]}"
                )

            raise RuntimeError(f"FIRMS returned {response.status_code}")

        except (requests.RequestException, RuntimeError) as error:
            last_error = error
            print(f"  failed: {error}")
            if attempt < MAX_ATTEMPTS and not str(error).startswith(
                "FIRMS rejected"
            ):
                print(f"  retrying in {RETRY_WAIT_SECONDS}s...")
                time.sleep(RETRY_WAIT_SECONDS)
            else:
                break

    raise RuntimeError(f"All {MAX_ATTEMPTS} attempts failed: {last_error}")


def main() -> Path:
    df = fetch()

    if len(df) < MIN_EXPECTED_ROWS:
        raise RuntimeError(
            f"Only {len(df)} detections returned - that is too few for a "
            "worldwide day. Refusing to save, so the last good file stays "
            "in place."
        )

    output_dir = ML_ROOT / "data" / "raw" / "firms"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"firms_world_{timestamp}.csv"
    df.to_csv(output_file, index=False)

    print(f"\nDetections downloaded: {len(df):,}")
    print(f"Date range: {df['acq_date'].min()} to {df['acq_date'].max()}")
    print(f"Saved to: {output_file}")
    return output_file


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nDOWNLOAD FAILED: {error}", file=sys.stderr)
        sys.exit(1)
