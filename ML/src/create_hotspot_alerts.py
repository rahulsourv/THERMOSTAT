"""
Turn live FIRMS detections into alerts using the PLACE-level model.

The important idea: the model scores PLACES, not pixels. A live detection
cannot tell us on its own whether somewhere is industrial - one night of
heat looks the same everywhere. So we look up what that place did during
the whole of 2025 and let the history do the talking.

  live detection -> which 5 km cell is it in?
                 -> what did that cell do across 2025?
                 -> what does the model say about that cell?
                 -> combine with tonight's intensity -> alert
"""

from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIR = Path("data/raw/firms")
SCORES_FILE = Path("data/processed/hotspot_scores_enriched.csv")
EVENTS_FILE = Path("data/processed/event_predictions_2025.csv")
OUTPUT_FILE = Path("data/processed/live_hotspot_alerts.csv")

GRID_SIZE = 0.05
LAT_OFFSET, LON_OFFSET = 2000, 4000

latest_live_file = max(RAW_DIR.glob("*.csv"), key=lambda f: f.stat().st_mtime)
live = pd.read_csv(latest_live_file)
print(f"Live file: {latest_live_file.name}")
print(f"Live detections: {len(live):,}")

history = pd.read_csv(
    SCORES_FILE,
    usecols=[
        "cell_id", "static_probability", "active_days", "months_active",
        "night_fraction", "total_detections", "label",
        "is_volcanic", "km_to_volcano", "km_to_thermal_plant",
        "near_power_plant",
    ],
)
print(f"Known places from 2025: {len(history):,}")

# Put each live detection into the same 5 km grid the model was built on.
lat_cell = np.floor(live["latitude"] / GRID_SIZE).astype(int)
lon_cell = np.floor(live["longitude"] / GRID_SIZE).astype(int)
live["cell_id"] = (lat_cell + LAT_OFFSET) * 10000 + (lon_cell + LON_OFFSET)

alerts = live.merge(history, on="cell_id", how="left")

# SIH26162 stage 2: what KIND of source is this place? Optional, so the
# pipeline still runs before the event classifier has been trained.
if EVENTS_FILE.exists():
    events = pd.read_csv(
        EVENTS_FILE,
        usecols=["cell_id", "final_class", "class_source", "class_confidence"],
    ).rename(columns={"final_class": "event_class"})
    alerts = alerts.merge(events, on="cell_id", how="left")
    print(f"Classified places loaded: {len(events):,}")
else:
    alerts["event_class"] = None
    alerts["class_source"] = None
    alerts["class_confidence"] = np.nan
    print("No event classifier output yet - event_class left empty.")

# A detection at a place with no 2025 history cannot be typed from history.
alerts["event_class"] = alerts["event_class"].fillna("unclassified")
alerts["class_source"] = alerts["class_source"].fillna("none")

alerts["known_place"] = alerts["static_probability"].notna()
alerts["static_probability"] = alerts["static_probability"].fillna(0.0)
alerts["active_days"] = alerts["active_days"].fillna(0)
alerts["months_active"] = alerts["months_active"].fillna(0)
alerts["is_volcanic"] = alerts["is_volcanic"].fillna(False).astype(bool)
alerts["near_power_plant"] = alerts["near_power_plant"].fillna(False).astype(bool)

# Tonight's intensity, squashed into 0-1 so one huge fire cannot dominate.
frp_component = (alerts["frp"].rank(pct=True)).fillna(0)

# The place's history is what we mostly trust; tonight's heat is a nudge.
alerts["alert_score"] = (
    100 * (0.80 * alerts["static_probability"] + 0.20 * frp_component)
).round(1)


def alert_level(row):
    # A volcano is a genuine persistent static source, but it is natural.
    # It gets its own category instead of polluting the industrial alerts.
    if row["is_volcanic"] and row["static_probability"] >= 0.60:
        return "Natural (volcano)"
    if row["static_probability"] >= 0.90 and row["known_place"]:
        return "High"
    if row["static_probability"] >= 0.60:
        return "Medium"
    return "Low"


alerts["alert_level"] = alerts.apply(alert_level, axis=1)


def explain(row):
    """Say WHY in plain words, so a human can check the claim."""
    if not row["known_place"]:
        return "New location - no 2025 history at this place"
    parts = [f"active {int(row['active_days'])} days in 2025"]
    if row["months_active"] >= 10:
        parts.append(f"in {int(row['months_active'])} of 12 months")
    if row["night_fraction"] >= 0.6:
        parts.append(f"{row['night_fraction']:.0%} at night")
    if row["is_volcanic"]:
        parts.append(f"volcano {row['km_to_volcano']:.1f} km away - NATURAL")
    elif row["near_power_plant"]:
        parts.append(
            f"CONFIRMED: power plant {row['km_to_thermal_plant']:.1f} km away"
        )
    return ", ".join(parts)


alerts["why"] = alerts.apply(explain, axis=1)

alerts = alerts.sort_values("alert_score", ascending=False)
alerts.to_csv(OUTPUT_FILE, index=False)

counts = alerts["alert_level"].value_counts()
print(f"\nMatched to a known 2025 place: {int(alerts['known_place'].sum()):,}")
print(f"New locations (no history):    {int((~alerts['known_place']).sum()):,}")
print("\nAlert levels:")
for level in ["High", "Medium", "Low", "Natural (volcano)"]:
    print(f"  {level:18s} {counts.get(level, 0):,}")

print("\nEvent classes in tonight's detections:")
for name, count in alerts["event_class"].value_counts().items():
    print(f"  {name:24s} {count:,}")

high = alerts[alerts["alert_level"] == "High"]
confirmed = int(high["near_power_plant"].sum())
print(
    f"\nOf {len(high):,} High alerts, {confirmed:,} "
    f"({confirmed / max(len(high), 1):.1%}) sit within 2 km of a "
    "known thermal power plant."
)

print("\nTop 10 alerts:")
print(
    alerts.head(10)[
        ["latitude", "longitude", "frp", "static_probability",
         "alert_score", "alert_level", "why"]
    ].to_string(index=False)
)
print(f"\nSaved to: {OUTPUT_FILE}")
