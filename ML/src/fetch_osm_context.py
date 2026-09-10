"""
Bulk OpenStreetMap context for the persistent thermal places.

Why not reuse enrich_labels_with_osm.py: that asks Overpass about ONE place
per HTTP request. For 6,900 places that is 6,900 requests and several hours
of a public, rate-limited service.

Instead this packs BATCH_PLACES `around` clauses into a single query. The
response loses track of which place each feature belongs to, but that is
recoverable offline with a KD-tree, so nothing is actually lost. ~175
requests instead of ~6,900.

The tag list is deliberately narrow. Broad tags like landuse=industrial
match entire city districts and blow up the response, and they are weak
evidence anyway - a hotspot inside an industrial estate could be anything.

Resumable: every batch is cached to its own file, so an interrupted run
picks up where it stopped instead of starting over.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

SCORES_FILE = Path("data/processed/hotspot_scores_enriched.csv")
CACHE_DIR = Path("data/external/osm_batches")
OUTPUT_FILE = Path("data/external/osm_features.csv")

# The kumi mirror timed out on every single request from here, so it is not
# in the rotation - falling back to it just cost 90s per batch. overpass-api.de
# answers in ~15s but returns a transient 504 fairly often, which is what the
# retry budget below is for.
OVERPASS_URLS = ["https://overpass-api.de/api/interpreter"]

MIN_STATIC_PROBABILITY = 0.60
BATCH_PLACES = 40
RADIUS_M = 3000
REQUEST_TIMEOUT = 90
MAX_ATTEMPTS = 6
POLITE_DELAY_S = 1.5

# (overpass filter, the class it is evidence for)
TAG_FILTERS = [
    ('["landuse"="quarry"]',            "mining"),
    ('["man_made"="mineshaft"]',        "mining"),
    ('["man_made"="flare"]',            "gas_flare"),
    ('["man_made"="petroleum_well"]',   "gas_flare"),
    ('["man_made"="works"]',            "industrial_works"),
    ('["power"="plant"]',               "power_plant"),
    ('["industrial"]',                  "industrial_works"),
]


def build_query(places) -> str:
    clauses = []
    for _, row in places.iterrows():
        for tag_filter, _kind in TAG_FILTERS:
            clauses.append(
                f"  nwr(around:{RADIUS_M},{row.latitude:.5f},"
                f"{row.longitude:.5f}){tag_filter};"
            )
    body = "\n".join(clauses)
    return f"[out:json][timeout:{REQUEST_TIMEOUT}];\n(\n{body}\n);\nout center tags;"


def post(query: str, attempt: int) -> list[dict]:
    """One Overpass call, rotating mirrors so a single slow host cannot stall
    the whole run."""
    url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
    response = requests.post(
        url,
        data={"data": query},
        headers={"User-Agent": "ThermoStats SIH26162 student research"},
        timeout=REQUEST_TIMEOUT + 30,
    )
    response.raise_for_status()
    return response.json().get("elements", [])


def coordinates(element: dict):
    if "lat" in element and "lon" in element:
        return element["lat"], element["lon"]
    center = element.get("center")
    return (center["lat"], center["lon"]) if center else None


def classify_tags(tags: dict) -> str:
    """Map OSM tags to the evidence class we care about.

    Order matters: a refinery is tagged man_made=works AND industrial=oil,
    and the more specific reading wins.
    """
    industrial = (tags.get("industrial") or "").lower()
    works = (tags.get("product") or tags.get("works") or "").lower()
    name = (tags.get("name") or "").lower()
    blob = f"{industrial} {works} {name}"

    if tags.get("man_made") in {"flare", "petroleum_well"}:
        return "gas_flare"
    if tags.get("landuse") == "quarry" or tags.get("man_made") == "mineshaft":
        return "mining"
    if any(word in blob for word in ("refinery", "petrochemical", "petroleum", "oil")):
        return "oil_refinery"
    if any(word in blob for word in ("brick", "kiln", "cement", "lime")):
        return "kiln"
    if any(word in blob for word in ("steel", "smelt", "foundry", "metal", "aluminium")):
        return "smelter"
    if tags.get("power") == "plant":
        return "power_plant"
    if tags.get("man_made") == "works" or industrial:
        return "industrial_works"
    return "other"


def main() -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    places = pd.read_csv(
        SCORES_FILE, usecols=["cell_id", "latitude", "longitude", "static_probability"]
    )
    places = places[places.static_probability >= MIN_STATIC_PROBABILITY]
    places = places.sort_values(["latitude", "longitude"]).reset_index(drop=True)

    batches = [
        places.iloc[i : i + BATCH_PLACES]
        for i in range(0, len(places), BATCH_PLACES)
    ]
    print(f"Places to enrich: {len(places):,}")
    print(f"Batches of {BATCH_PLACES}: {len(batches)}\n", flush=True)

    done = failed = 0
    for number, batch in enumerate(batches):
        cache_file = CACHE_DIR / f"batch_{number:04d}.json"
        if cache_file.exists():
            done += 1
            continue

        query = build_query(batch)
        elements = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                elements = post(query, attempt)
                break
            except Exception as error:
                wait = min(8 * (attempt + 1), 40)
                print(f"  batch {number}: attempt {attempt+1} failed "
                      f"({type(error).__name__}), retrying in {wait}s", flush=True)
                time.sleep(wait)

        if elements is None:
            failed += 1
            print(f"  batch {number}: GIVING UP", flush=True)
            continue

        rows = []
        for element in elements:
            point = coordinates(element)
            if point is None:
                continue
            tags = element.get("tags", {})
            rows.append({
                "osm_id": f"{element.get('type')}/{element.get('id')}",
                "latitude": point[0],
                "longitude": point[1],
                "osm_class": classify_tags(tags),
                "name": tags.get("name", ""),
            })

        cache_file.write_text(json.dumps(rows), encoding="utf-8")
        done += 1
        if done % 10 == 0 or number == len(batches) - 1:
            print(f"  {done}/{len(batches)} batches  "
                  f"({failed} failed)  last returned {len(rows)} features",
                  flush=True)
        time.sleep(POLITE_DELAY_S)

    # ---- Combine every cached batch into one table -----------------------
    all_rows = []
    for cache_file in sorted(CACHE_DIR.glob("batch_*.json")):
        all_rows.extend(json.loads(cache_file.read_text(encoding="utf-8")))

    if not all_rows:
        print("No OSM features collected.")
        return 1

    features = pd.DataFrame(all_rows).drop_duplicates(subset="osm_id")
    features = features[features.osm_class != "other"]
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(OUTPUT_FILE, index=False)

    print(f"\nBatches done: {done}/{len(batches)}  (failed {failed})")
    print(f"Unique OSM features: {len(features):,}")
    print(features.osm_class.value_counts().to_string())
    print(f"\nSaved to: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
