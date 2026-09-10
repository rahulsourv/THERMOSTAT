"""
Build the SIH26162 event taxonomy: what KIND of thermal source is this?

The existing model answers one question - is this place a persistent static
source, or a transient fire? That is stage 1 and it stays. This adds stage 2:
given the answer, what type of event is it?

    stage 1  static_probability      persistent  vs  transient
    stage 2a persistent  -> gas flare / power plant / refinery /
                            industrial heat / mining / volcano
    stage 2b transient   -> agricultural burning / wildfire

Where the labels come from matters, and the two halves are NOT equal:

  ANCHORED (real, independent ground truth). Volcanoes from Smithsonian GVP,
  thermal power plants from WRI, mines/refineries/flares/works from
  OpenStreetMap. None of these came from NASA, so a model that learns to
  predict them from satellite behaviour has learned something real, and can
  then label the places nobody has mapped.

  HEURISTIC (a definition, not a discovery). Agricultural burning vs wildfire
  has no ground-truth source here and no landcover raster, so it is separated
  by fire radiative power, day/night mix and seasonality. Training a model on
  these would only teach it to reproduce the rule, so the rule is applied
  directly and reported as a rule. Do not quote accuracy figures for it.

Only the anchored rows become training data. That is the honest split.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

SCORES_FILE = Path("data/processed/hotspot_scores_enriched.csv")
OSM_FILE = Path("data/external/osm_features.csv")
OUTPUT_FILE = Path("data/processed/event_labels_2025.csv")

EARTH_RADIUS_KM = 6371.0
OSM_MATCH_KM = 3.0

PERSISTENT_MIN = 0.90     # stage-1 cut for "this place is a static source"
TRANSIENT_MAX = 0.50

# Thresholds below are read off the measured distributions of the 680,008
# transient places, not guessed. Median transient frp_max is 18 MW and the
# 90th percentile is 77, so 75 sits at the top of the ordinary-fire range.
WILDFIRE_FRP_MAX = 75.0
WILDFIRE_NIGHT_FRP = 30.0    # a fire still burning at night, with real power
AGRI_NIGHT_FRACTION = 0.40   # crop residue is burnt in daylight
AGRI_MAX_MONTHS = 5          # and inside one short season

# OSM evidence class -> our event class
OSM_TO_EVENT = {
    "gas_flare": "gas_flare",
    "mining": "mining",
    "oil_refinery": "oil_refinery",
    "kiln": "industrial_heat",
    "smelter": "industrial_heat",
    "industrial_works": "industrial_heat",
    "power_plant": "thermal_power_plant",
}

EVENT_CLASSES = [
    "gas_flare", "thermal_power_plant", "oil_refinery", "industrial_heat",
    "mining", "volcano", "agricultural_burning", "wildfire", "unknown",
]


def to_xyz(lat, lon):
    lat_r, lon_r = np.radians(lat), np.radians(lon)
    return np.column_stack([
        np.cos(lat_r) * np.cos(lon_r),
        np.cos(lat_r) * np.sin(lon_r),
        np.sin(lat_r),
    ])


def nearest_osm(places, osm):
    """Nearest OSM feature per place, as (class, distance_km)."""
    tree = cKDTree(to_xyz(osm.latitude.values, osm.longitude.values))
    chord, index = tree.query(to_xyz(places.latitude.values, places.longitude.values))
    # chord length on a unit sphere -> great-circle km
    km = 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2, 0, 1))
    return osm.osm_class.values[index], km


def main():
    df = pd.read_csv(SCORES_FILE)
    print(f"Places: {len(df):,}")

    df["event_class"] = "unknown"
    df["label_source"] = "none"
    df["osm_class"] = ""
    df["km_to_osm"] = np.nan

    # ---- OSM evidence (optional; the file may not exist yet) -------------
    if OSM_FILE.exists():
        osm = pd.read_csv(OSM_FILE)
        osm = osm[osm.osm_class.isin(OSM_TO_EVENT)]
        if len(osm):
            osm_class, km = nearest_osm(df, osm)
            df["osm_class"] = osm_class
            df["km_to_osm"] = km
            hit = km <= OSM_MATCH_KM
            df.loc[hit, "event_class"] = [
                OSM_TO_EVENT[c] for c in df.loc[hit, "osm_class"]
            ]
            df.loc[hit, "label_source"] = "osm"
            print(f"OSM features: {len(osm):,}  ->  {int(hit.sum()):,} places matched")
    else:
        print("No OSM file yet - anchoring on volcanoes and power plants only.")

    # ---- Stronger anchors override OSM -----------------------------------
    # WRI is a curated plant register; OSM industrial tagging around a plant
    # is often just the surrounding estate, so WRI wins where they disagree.
    plant = df.near_power_plant.fillna(False).astype(bool)
    df.loc[plant, "event_class"] = "thermal_power_plant"
    df.loc[plant, "label_source"] = "wri_power_plant"

    # A volcano outranks everything: it is natural, and mislabelling one as
    # industrial is the single most damaging error this system can make.
    volcano = df.is_volcanic.fillna(False).astype(bool)
    df.loc[volcano, "event_class"] = "volcano"
    df.loc[volcano, "label_source"] = "smithsonian_gvp"

    anchored = df.label_source != "none"
    print(f"\nAnchored places (training data): {int(anchored.sum()):,}")
    print(df.loc[anchored, "event_class"].value_counts().to_string())

    # ---- Heuristic branch for transient fires ----------------------------
    transient = df.static_probability < TRANSIENT_MAX
    unlabelled = df.label_source == "none"

    wildfire = transient & unlabelled & (
        (df.frp_max >= WILDFIRE_FRP_MAX)
        | ((df.night_fraction >= AGRI_NIGHT_FRACTION)
           & (df.frp_max >= WILDFIRE_NIGHT_FRP))
    )
    df.loc[wildfire, "event_class"] = "wildfire"
    df.loc[wildfire, "label_source"] = "heuristic"

    agri = transient & (df.label_source == "none") & (
        (df.night_fraction < AGRI_NIGHT_FRACTION)
        & (df.months_active <= AGRI_MAX_MONTHS)
    )
    df.loc[agri, "event_class"] = "agricultural_burning"
    df.loc[agri, "label_source"] = "heuristic"

    # ---- Persistent but unmapped: the interesting unknowns ---------------
    # These are the places the classifier exists to name.
    persistent_unmapped = (df.static_probability >= PERSISTENT_MIN) & (
        df.label_source == "none"
    )
    print(f"\nPersistent but unmapped (model will classify these): "
          f"{int(persistent_unmapped.sum()):,}")

    print("\nFinal label distribution:")
    print(df.event_class.value_counts().to_string())
    print("\nBy source:")
    print(df.label_source.value_counts().to_string())

    keep = [
        "cell_id", "latitude", "longitude", "static_probability",
        "event_class", "label_source", "osm_class", "km_to_osm",
        "is_volcanic", "near_power_plant", "km_to_thermal_plant",
    ]
    df[keep].to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
