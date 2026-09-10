"""Add cautious OpenStreetMap evidence to an initial hotspot-labelling batch."""

from __future__ import annotations

import math
import os
import time
from pathlib import Path

import pandas as pd
import requests


SOURCE_FILE = Path("data/processed/hotspot_labeling_sample.csv")
OUTPUT_FILE = Path("data/processed/hotspot_labeling_sample_osm.csv")
OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"
BATCH_SIZE = int(os.getenv("THERMOSTATS_BATCH_SIZE", "1"))
START_INDEX = int(os.getenv("THERMOSTATS_START_INDEX", "0"))
RADIUS_METERS = 3_000


def distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return approximate great-circle distance in metres."""
    earth_radius = 6_371_000
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * earth_radius * math.asin(math.sqrt(value))


def query_industrial_features(latitude: float, longitude: float) -> list[dict]:
    """Fetch nearby mapped industrial features from OpenStreetMap via Overpass."""
    query = f"""
    [out:json][timeout:30];
    (
      nwr(around:{RADIUS_METERS},{latitude},{longitude})[\"power\"=\"plant\"];
      nwr(around:{RADIUS_METERS},{latitude},{longitude})[\"man_made\"=\"works\"];
      nwr(around:{RADIUS_METERS},{latitude},{longitude})[\"man_made\"=\"flare\"];
      nwr(around:{RADIUS_METERS},{latitude},{longitude})[\"man_made\"=\"petroleum_well\"];
      nwr(around:{RADIUS_METERS},{latitude},{longitude})[\"landuse\"=\"industrial\"];
      nwr(around:{RADIUS_METERS},{latitude},{longitude})[\"industrial\"];
      nwr(around:{RADIUS_METERS},{latitude},{longitude})[\"landuse\"=\"quarry\"];
    );
    out center tags;
    """
    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers={
            "User-Agent": "ThermoStats student research project",
            "Accept": "application/json",
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("elements", [])


def describe_feature(feature: dict) -> tuple[str, bool]:
    """Return a compact description and whether its OSM tag is strong evidence."""
    tags = feature.get("tags", {})
    name = tags.get("name", "Unnamed feature")
    feature_type = (
        tags.get("power")
        or tags.get("man_made")
        or tags.get("industrial")
        or tags.get("landuse")
        or "industrial feature"
    )
    strong = (
        tags.get("power") == "plant"
        or tags.get("man_made") in {"works", "flare", "petroleum_well"}
        or tags.get("landuse") == "quarry"
    )
    return f"{name} ({feature_type})", strong


def feature_coordinates(feature: dict) -> tuple[float, float] | None:
    if "lat" in feature and "lon" in feature:
        return feature["lat"], feature["lon"]
    center = feature.get("center")
    if center:
        return center["lat"], center["lon"]
    return None


def main() -> None:
    input_file = OUTPUT_FILE if OUTPUT_FILE.exists() else SOURCE_FILE
    df = pd.read_csv(input_file)

    # Empty CSV columns are otherwise inferred as floats by pandas.
    for column in ["label", "label_source", "review_notes"]:
        df[column] = df[column].astype(object)

    for column in ["osm_feature_count", "nearest_osm_feature_m", "auto_label"]:
        if column not in df.columns:
            df[column] = pd.NA
    df["auto_label"] = df["auto_label"].astype(object)

    batch = df.iloc[START_INDEX : START_INDEX + BATCH_SIZE].copy()

    for index, row in batch.iterrows():
        hotspot_id = row["hotspot_id"]
        latitude = row["latitude"]
        longitude = row["longitude"]
        print(f"Checking {hotspot_id}...", flush=True)

        try:
            features = query_industrial_features(latitude, longitude)
        except requests.RequestException as error:
            print(f"  Skipped: {error}", flush=True)
            df.to_csv(OUTPUT_FILE, index=False)
            continue

        nearby = []
        for feature in features:
            coordinates = feature_coordinates(feature)
            if coordinates is None:
                continue
            feature_lat, feature_lon = coordinates
            distance = distance_meters(latitude, longitude, feature_lat, feature_lon)
            description, strong = describe_feature(feature)
            nearby.append((distance, description, strong))

        nearby.sort(key=lambda item: item[0])

        df.loc[index, "osm_feature_count"] = len(nearby)

        if not nearby:
            df.loc[index, "auto_label"] = "uncertain"
            df.loc[index, "label"] = "uncertain"
            df.loc[index, "label_source"] = "osm_first_pass"
            df.loc[index, "review_notes"] = "No matching OSM industrial feature within 3 km"
        else:
            nearest_distance, nearest_description, strong_evidence = nearby[0]
            df.loc[index, "nearest_osm_feature_m"] = round(nearest_distance)

            if strong_evidence and nearest_distance <= 1_000:
                df.loc[index, "auto_label"] = "industrial"
                df.loc[index, "label"] = "industrial"
                df.loc[index, "label_source"] = "osm_first_pass"
                df.loc[index, "review_notes"] = (
                    f"Strong OSM feature within {nearest_distance:.0f} m: "
                    f"{nearest_description}"
                )
            else:
                df.loc[index, "auto_label"] = "uncertain"
                df.loc[index, "label"] = "uncertain"
                df.loc[index, "label_source"] = "osm_first_pass"
                df.loc[index, "review_notes"] = (
                    f"Nearest OSM feature {nearest_distance:.0f} m away: "
                    f"{nearest_description}"
                )

        # Save after each lookup so a long run never loses completed labels.
        df.to_csv(OUTPUT_FILE, index=False)

        # Respect the public Overpass service: one request at a time.
        time.sleep(1.2)

    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved enriched labels to: {OUTPUT_FILE}")
    print(df.head(BATCH_SIZE)[["hotspot_id", "label", "auto_label", "review_notes"]])


if __name__ == "__main__":
    main()
