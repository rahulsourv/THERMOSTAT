"""
Build a stratified sample of Stage-2b candidates for MANUAL verification.

WHY A PROVISIONAL LABEL IS SHOWN AT ALL

  The sample must cover every class, and the only thing that can stratify it
  today is the nearest mapped OSM feature. So that is used to CHOOSE the
  sample - and nothing else. It is presented in the tool as a suggestion to be
  judged, never as the answer, and the verified class is entered independently.

  This is the distinction the whole exercise rests on: nearest-feature is fine
  for deciding what to look at, and unfit for deciding what a thing is. A
  refinery carries flare, works and industrial tags at once, so "nearest" picks
  a class by accident of geometry.

SPATIAL SPREAD

  Sampling the top candidates by score would return fifty sites from one
  Iraqi oil field. Selection is therefore round-robin across 10-degree cells,
  so the reviewer sees the range of appearances a class actually takes.

OSM TAGS

  data/external/osm_features.csv kept only a derived class and a name - the raw
  tags were dropped during bulk collection. The reviewer needs the real tags to
  judge, so this re-queries Overpass for the sampled sites only.

Writes data/processed/verification_sample.json. Trains nothing.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.spatial import cKDTree

SCORES_FILE = Path("data/processed/stage1_m2_scores.csv")
FEATURES_FILE = Path("data/processed/hotspot_features_2025_v2.csv")
OSM_FILE = Path("data/external/osm_features.csv")
DBSCAN_FILE = Path("data/processed/dbscan_clusters.csv")
DBSCAN_SUMMARY = Path("data/processed/dbscan_cluster_summary.csv")
OUT_FILE = Path("data/processed/verification_sample.json")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
EARTH_RADIUS_KM = 6371.0

STAGE1_MIN = 0.5
OSM_MATCH_KM = 3.0
CONTEXT_RADIUS_M = 1500      # what the reviewer sees around the point
PER_CLASS = 50
SPATIAL_BIN_DEG = 10
BATCH_SITES = 25
REQUEST_TIMEOUT = 120
MAX_ATTEMPTS = 4

# Which provisional bucket each OSM class puts a site in. Kiln and smelter are
# both "a factory with a furnace", so they share a bucket.
PROVISIONAL = {
    "gas_flare": "gas_flare",
    "power_plant": "power_plant",
    "mining": "mining",
    "oil_refinery": "refinery",
    "kiln": "factory",
    "smelter": "factory",
    "industrial_works": "other_industrial",
}

THERMAL_COLS = [
    "total_detections", "active_days", "duty_cycle", "span_days",
    "longest_gap_days", "months_active", "month_cv", "peak_month_share",
    "night_fraction", "frp_mean", "frp_max", "frp_std", "frp_cv",
    "ti4_mean", "ti4_std", "ti5_mean", "ti4_minus_ti5_mean",
    "spread_km", "active_neighbours",
]


def xyz(lat, lon):
    la, lo = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    return np.column_stack([np.cos(la) * np.cos(lo),
                            np.cos(la) * np.sin(lo), np.sin(la)])


def spatially_spread(group: pd.DataFrame, n: int) -> pd.DataFrame:
    """Round-robin across coarse geographic bins so one basin cannot dominate."""
    g = group.copy()
    g["bin"] = (np.floor(g.latitude / SPATIAL_BIN_DEG).astype(int).astype(str) + "_"
                + np.floor(g.longitude / SPATIAL_BIN_DEG).astype(int).astype(str))
    g = g.sample(frac=1.0, random_state=42)          # break within-bin order
    picked, seen = [], {b: 0 for b in g["bin"].unique()}
    while len(picked) < n:
        added = False
        for b in list(seen):
            pool = g[(g["bin"] == b)].iloc[seen[b]:seen[b] + 1]
            if len(pool):
                picked.append(pool)
                seen[b] += 1
                added = True
                if len(picked) >= n:
                    break
        if not added:
            break
    return pd.concat(picked).head(n) if picked else g.head(n)


def fetch_tags(sites: pd.DataFrame) -> dict:
    """Full OSM tags around each sampled site, batched to be polite."""
    out = {int(c): [] for c in sites.cell_id}
    batches = [sites.iloc[i:i + BATCH_SITES]
               for i in range(0, len(sites), BATCH_SITES)]
    print(f"\nFetching OSM tags for {len(sites)} sites in {len(batches)} batches...")

    for n, batch in enumerate(batches, 1):
        clauses = "\n".join(
            f'  nwr(around:{CONTEXT_RADIUS_M},{r.latitude:.5f},{r.longitude:.5f});'
            for r in batch.itertuples())
        query = (f"[out:json][timeout:{REQUEST_TIMEOUT}];\n(\n{clauses}\n);\n"
                 "out center tags;")

        elements = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = requests.post(
                    OVERPASS_URL, data={"data": query},
                    headers={"User-Agent": "ThermoStats SIH26162 verification"},
                    timeout=REQUEST_TIMEOUT + 30)
                resp.raise_for_status()
                elements = resp.json().get("elements", [])
                break
            except Exception as exc:
                wait = 8 * (attempt + 1)
                print(f"  batch {n}: attempt {attempt+1} failed "
                      f"({type(exc).__name__}), retry in {wait}s")
                time.sleep(wait)
        if elements is None:
            print(f"  batch {n}: GAVE UP")
            continue

        # Overpass returns one flat list; assign each feature to nearby sites.
        feats = []
        for el in elements:
            tags = el.get("tags") or {}
            if not tags:
                continue
            if "lat" in el and "lon" in el:
                lat, lon = el["lat"], el["lon"]
            elif el.get("center"):
                lat, lon = el["center"]["lat"], el["center"]["lon"]
            else:
                continue
            feats.append((lat, lon, el.get("type"), el.get("id"), tags))

        if feats:
            tree = cKDTree(xyz([f[0] for f in feats], [f[1] for f in feats]))
            radius_chord = 2 * np.sin(
                (CONTEXT_RADIUS_M / 1000) / (2 * EARTH_RADIUS_KM))
            for r in batch.itertuples():
                idx = tree.query_ball_point(
                    xyz([r.latitude], [r.longitude])[0], radius_chord)
                rows = []
                for i in idx:
                    lat, lon, kind, oid, tags = feats[i]
                    d = 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(
                        np.linalg.norm(xyz([lat], [lon])[0]
                                       - xyz([r.latitude], [r.longitude])[0]) / 2,
                        0, 1))
                    rows.append({"osm_id": f"{kind}/{oid}",
                                 "km": round(float(d), 3),
                                 "name": tags.get("name", ""),
                                 "tags": tags})
                rows.sort(key=lambda x: x["km"])
                out[int(r.cell_id)] = rows[:25]

        print(f"  batch {n}/{len(batches)} ok ({len(feats)} tagged features)")
        time.sleep(1.5)
    return out


def main():
    scores = pd.read_csv(SCORES_FILE)
    feats = pd.read_csv(FEATURES_FILE)
    osm = pd.read_csv(OSM_FILE)

    cand = scores[scores.score_raw >= STAGE1_MIN].merge(
        feats[["cell_id"] + THERMAL_COLS], on="cell_id", how="left")

    chord, idx = cKDTree(xyz(osm.latitude, osm.longitude)).query(
        xyz(cand.latitude, cand.longitude))
    cand["km_to_osm"] = 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2, 0, 1))
    cand["nearest_osm_class"] = osm.osm_class.values[idx]
    cand["nearest_osm_name"] = osm.name.fillna("").values[idx]

    pool = cand[cand.km_to_osm <= OSM_MATCH_KM].copy()
    pool["provisional"] = pool.nearest_osm_class.map(PROVISIONAL)
    pool = pool[pool.provisional.notna()]
    print(f"Stage-2b candidates with OSM within {OSM_MATCH_KM} km: {len(pool):,}")
    print(pool.provisional.value_counts().to_string())

    picks = [spatially_spread(g, PER_CLASS)
             for _, g in pool.groupby("provisional")]
    sample = pd.concat(picks).reset_index(drop=True)
    print(f"\nSampled {len(sample)} sites "
          f"({PER_CLASS} per provisional class, spatially spread)")
    print(sample.provisional.value_counts().to_string())

    # DBSCAN context, where the cell happens to be in a cluster.
    db = pd.read_csv(DBSCAN_FILE, usecols=["cell_id", "cluster"])
    summ = pd.read_csv(DBSCAN_SUMMARY)
    sample = sample.merge(db, on="cell_id", how="left")
    sample = sample.merge(
        summ[["cluster", "points", "extent_km", "verdict", "dominant_osm_class"]]
        .rename(columns={"points": "cluster_points",
                         "extent_km": "cluster_extent_km",
                         "verdict": "cluster_verdict",
                         "dominant_osm_class": "cluster_dominant_osm"}),
        on="cluster", how="left")

    tags = fetch_tags(sample)

    records = []
    for r in sample.itertuples():
        cid = int(r.cell_id)
        records.append({
            "cell_id": cid,
            "latitude": round(float(r.latitude), 6),
            "longitude": round(float(r.longitude), 6),
            "provisional_class": r.provisional,
            "nearest_osm_class": r.nearest_osm_class,
            "nearest_osm_name": r.nearest_osm_name or "",
            "km_to_nearest_osm": round(float(r.km_to_osm), 3),
            "stage1_score": round(float(r.score_raw), 4),
            "thermal": {c: (None if pd.isna(getattr(r, c))
                            else round(float(getattr(r, c)), 4))
                        for c in THERMAL_COLS},
            "dbscan": (None if pd.isna(r.cluster) or r.cluster == -1 else {
                "cluster": int(r.cluster),
                "points": int(r.cluster_points) if pd.notna(r.cluster_points) else None,
                "extent_km": float(r.cluster_extent_km) if pd.notna(r.cluster_extent_km) else None,
                "verdict": r.cluster_verdict if pd.notna(r.cluster_verdict) else None,
                "dominant_osm": r.cluster_dominant_osm if pd.notna(r.cluster_dominant_osm) else None,
            }),
            "osm_features": tags.get(cid, []),
        })

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(records, indent=1), encoding="utf-8")
    with_tags = sum(1 for r in records if r["osm_features"])
    print(f"\nSaved {len(records)} sites to {OUT_FILE}")
    print(f"  with OSM tag context: {with_tags}")
    print(f"  in a DBSCAN cluster : {sum(1 for r in records if r['dbscan'])}")


if __name__ == "__main__":
    main()
