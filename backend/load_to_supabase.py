"""
Load the ML output into Supabase.

Speed note: this does NOT insert row by row. 687,000 separate INSERT
statements over the internet would take hours. Instead it uses Postgres
COPY, which streams the whole table in one go and takes seconds.

Two different jobs, on two different clocks:

  places  - the 2025 reference data the model scored. Only changes when you
            retrain on a new archive, which is roughly yearly.
  alerts  - tonight's detections. Changes every run.

So the daily pipeline loads ONLY alerts:

    python backend/load_to_supabase.py --alerts-only
    python backend/load_to_supabase.py --places-only
    python backend/load_to_supabase.py              (both)
"""

import argparse
import io
import sys
from pathlib import Path

import pandas as pd
import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.settings import connection_kwargs, describe

ROOT = Path(__file__).resolve().parents[1]
PLACES_CSV = ROOT / "ML" / "data" / "processed" / "hotspot_scores_enriched.csv"
ALERTS_CSV = ROOT / "ML" / "data" / "processed" / "live_hotspot_alerts.csv"

# Supabase free tier gives 500 MB. All 687k places fit comfortably once we
# keep only the columns the API actually serves. If you ever run out of
# space, raise this to 0.05 and only interesting places get uploaded.
MIN_PROBABILITY = 0.0

PLACE_COLUMNS = [
    "cell_id", "latitude", "longitude", "static_probability",
    "active_days", "months_active", "night_fraction", "total_detections",
    "duty_cycle", "frp_mean", "frp_std", "spread_km",
    "is_volcanic", "km_to_volcano", "near_power_plant",
    "km_to_thermal_plant", "label",
    # SIH26162 stage 2
    "event_class", "class_source", "class_confidence",
]

ALERT_COLUMNS = [
    "cell_id", "latitude", "longitude", "acq_date", "acq_time", "frp",
    "confidence", "daynight", "static_probability", "alert_score",
    "alert_level", "why", "known_place", "is_volcanic", "near_power_plant",
    # SIH26162 stage 2
    "event_class", "class_source", "class_confidence",
]

# The classification columns only exist after the stage-2 model has been
# trained. Before that the CSVs simply do not have them, and the loader
# should still work rather than crash a nightly run.
OPTIONAL_COLUMNS = {"event_class", "class_source", "class_confidence"}


def usable_columns(path, wanted):
    """Drop optional columns the CSV does not carry yet."""
    header = set(pd.read_csv(path, nrows=0).columns)
    missing = [c for c in wanted if c not in header]
    if missing:
        if set(missing) - OPTIONAL_COLUMNS:
            raise KeyError(f"{path.name} is missing required columns: "
                           f"{sorted(set(missing) - OPTIONAL_COLUMNS)}")
        print(f"  note: {path.name} has no {missing} yet - "
              "run the stage-2 model to populate them")
    return [c for c in wanted if c in header]


def copy_dataframe(cur, df, table, columns):
    """Stream a DataFrame into Postgres using COPY."""
    buffer = io.StringIO()
    df[columns].to_csv(buffer, index=False, header=False, na_rep="\\N")
    buffer.seek(0)
    cur.copy_expert(
        f"COPY {table} ({', '.join(columns)}) "
        "FROM STDIN WITH (FORMAT csv, NULL '\\N')",
        buffer,
    )


def load_places(cur):
    columns = usable_columns(PLACES_CSV, PLACE_COLUMNS)
    df = pd.read_csv(PLACES_CSV, usecols=columns)
    df = df[df["static_probability"] >= MIN_PROBABILITY]
    print(f"Uploading {len(df):,} places...")
    # Alerts reference places, so clear alerts first to avoid an orphan gap.
    cur.execute("TRUNCATE places RESTART IDENTITY;")
    copy_dataframe(cur, df, "places", columns)
    cur.execute("ANALYZE places;")
    return len(df)


def load_alerts(cur):
    columns = usable_columns(ALERTS_CSV, ALERT_COLUMNS)
    df = pd.read_csv(ALERTS_CSV, usecols=columns)
    df["acq_date"] = pd.to_datetime(df["acq_date"]).dt.date
    print(f"Uploading {len(df):,} alerts...")
    cur.execute("TRUNCATE alerts RESTART IDENTITY;")
    copy_dataframe(cur, df, "alerts", columns)
    cur.execute("ANALYZE alerts;")
    return len(df)


def main():
    parser = argparse.ArgumentParser(description="Load ML output into Supabase")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--alerts-only", action="store_true",
                       help="daily run: refresh tonight's alerts only")
    group.add_argument("--places-only", action="store_true",
                       help="after retraining: refresh the 2025 reference data")
    args = parser.parse_args()

    do_places = not args.alerts_only
    do_alerts = not args.places_only

    print(f"Connecting to Supabase: {describe()}")

    # One transaction. If anything fails, nothing is truncated - the old
    # data stays live rather than leaving the API serving an empty table.
    with psycopg2.connect(**connection_kwargs()) as conn:
        with conn.cursor() as cur:
            n_places = load_places(cur) if do_places else None
            n_alerts = load_alerts(cur) if do_alerts else None

            cur.execute("SELECT count(*) FROM places;")
            total_places = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM alerts;")
            total_alerts = cur.fetchone()[0]

    print(f"\nDone. Database holds {total_places:,} places "
          f"and {total_alerts:,} alerts.")
    return {"places": n_places, "alerts": n_alerts}


if __name__ == "__main__":
    main()
