"""
DBSCAN over the persistent FIRMS thermal anomalies, validated against OSM.

WHAT IS CLUSTERED, and why it is not the raw detection file:

  The unit here is a PLACE - a 0.05 degree (~5 km) cell summarising a year of
  VIIRS detections - filtered to the persistent ones (static_probability >=
  MIN_STATIC). Clustering raw nightly detections would mostly rediscover
  crop-burning season in the Punjab, which says nothing about industry.
  Clustering persistent places asks the question actually worth asking:
  do groups of steadily-hot cells sit on top of real industrial sites?

WHY HAVERSINE, NOT EUCLIDEAN ON LAT/LON:

  A degree of longitude is 111 km at the equator and 30 km at 74N. Running
  DBSCAN on raw degrees would silently use a different eps in Siberia than
  in Iraq. sklearn's haversine metric works in radians and returns great
  circle distance, so eps is a real number of kilometres everywhere.

WHY eps CANNOT BE SMALL:

  The places sit on a 0.05 degree grid, so two ADJACENT cells are already
  ~5.6 km apart in latitude. An eps below that makes every point its own
  island and DBSCAN returns 100% noise. The sweep in this script exists to
  show that rather than assert it.

Outputs:
  data/processed/dbscan_clusters.csv    one row per place, with cluster id
  models/dbscan_metrics.json            every metric reported here
  outputs/maps/dbscan_osm_validation.html   the interactive validation map
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.cluster import DBSCAN
from sklearn.metrics import silhouette_score

SCORES_FILE = Path("data/processed/hotspot_scores_enriched.csv")
OSM_FILE = Path("data/external/osm_features.csv")
CLUSTERS_FILE = Path("data/processed/dbscan_clusters.csv")
METRICS_FILE = Path("models/dbscan_metrics.json")
MAP_FILE = Path("outputs/maps/dbscan_osm_validation.html")

EARTH_RADIUS_KM = 6371.0
MIN_STATIC = 0.90          # what counts as a persistent thermal source

# Chosen after the sweep this script prints. 8 km is the smallest eps that
# can still join two diagonally adjacent 0.05 degree cells (~7.9 km apart),
# so it groups a contiguous industrial footprint without bridging separate
# facilities. min_samples=3 means a cluster needs a real footprint, not two
# lonely pixels.
EPS_KM = 8.0
MIN_SAMPLES = 3

SWEEP_EPS = [4.0, 6.0, 8.0, 12.0, 20.0]
SWEEP_MIN_SAMPLES = [2, 3, 5]

# A cluster counts as industrially confirmed if ANY of its member cells has a
# mapped industrial feature this close. 3 km is the OSM search radius used
# when the features were fetched, so a larger number here would claim
# evidence that was never looked for.
MATCH_KM = 3.0

SILHOUETTE_SAMPLE = 3000   # full pairwise on 5k points is 30M cells; sample


def to_radians(df):
    return np.radians(df[["latitude", "longitude"]].to_numpy())


def to_xyz(lat, lon):
    lat_r, lon_r = np.radians(lat), np.radians(lon)
    return np.column_stack([
        np.cos(lat_r) * np.cos(lon_r),
        np.cos(lat_r) * np.sin(lon_r),
        np.sin(lat_r),
    ])


def run_dbscan(points_rad, eps_km, min_samples):
    """DBSCAN with eps expressed in kilometres."""
    return DBSCAN(
        eps=eps_km / EARTH_RADIUS_KM,
        min_samples=min_samples,
        metric="haversine",
        algorithm="ball_tree",
    ).fit_predict(points_rad)


def sweep(points_rad, km_to_osm):
    """Show how eps and min_samples change the answer, rather than asserting
    one setting is correct.

    The confirmed% column is the one that matters: a setting that finds more
    clusters is not better if the extra clusters sit on nothing. Choosing eps
    by cluster count alone would be optimising for a number nobody cares about.
    """
    rows = []
    for eps in SWEEP_EPS:
        for min_samples in SWEEP_MIN_SAMPLES:
            labels = run_dbscan(points_rad, eps, min_samples)
            clustered = labels != -1
            ids = set(labels[clustered])
            n_clusters = len(ids)

            confirmed = 0
            if n_clusters:
                frame = pd.DataFrame({"cluster": labels, "km": km_to_osm})
                nearest = frame[clustered].groupby("cluster").km.min()
                confirmed = int((nearest <= MATCH_KM).sum())

            rows.append({
                "eps_km": eps,
                "min_samples": min_samples,
                "clusters": n_clusters,
                "noise_pct": round(100 * (~clustered).mean(), 1),
                "largest": int(pd.Series(labels[clustered]).value_counts().max())
                if n_clusters else 0,
                "osm_confirmed": confirmed,
                "confirmed_pct": round(100 * confirmed / n_clusters, 1)
                if n_clusters else 0.0,
            })
    return pd.DataFrame(rows)


def surveyed_cell_ids():
    """Which places has the Overpass fetch actually asked about yet?

    This matters more than it sounds. The fetch walks places sorted by
    latitude then longitude, 40 per batch, and it is still running. So whole
    regions - Siberia, northern China - currently have NO OpenStreetMap
    features simply because their batch has not run.

    Without this, a cluster in an unfetched region looks identical to a
    cluster standing on genuinely empty ground, and the analysis would report
    "false positive" when the honest answer is "not checked yet". The batch
    files on disk say exactly which places were covered, so reconstruct that
    rather than guessing from distance.
    """
    from fetch_osm_context import BATCH_PLACES, MIN_STATIC_PROBABILITY

    cache = Path("data/external/osm_batches")
    done = sorted(int(f.stem.split("_")[1]) for f in cache.glob("batch_*.json"))
    if not done:
        return set(), 0

    ordered = pd.read_csv(
        SCORES_FILE, usecols=["cell_id", "latitude", "longitude",
                              "static_probability"]
    )
    ordered = ordered[ordered.static_probability >= MIN_STATIC_PROBABILITY]
    ordered = ordered.sort_values(["latitude", "longitude"]).reset_index(drop=True)

    ids = set()
    for number in done:
        chunk = ordered.iloc[number * BATCH_PLACES:(number + 1) * BATCH_PLACES]
        ids.update(chunk.cell_id.tolist())
    return ids, len(done)


def cluster_extent_km(group):
    """Greatest distance between any two members - the cluster's footprint."""
    if len(group) < 2:
        return 0.0
    xyz = to_xyz(group.latitude.values, group.longitude.values)
    # Small clusters, so the full pairwise is cheap and exact.
    chord = np.sqrt(((xyz[:, None, :] - xyz[None, :, :]) ** 2).sum(-1))
    return float(2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord.max() / 2, 0, 1)))


def main():
    places = pd.read_csv(SCORES_FILE)
    places = places[places.static_probability >= MIN_STATIC].reset_index(drop=True)
    print(f"Persistent places (static_probability >= {MIN_STATIC}): {len(places):,}\n")

    points_rad = to_radians(places)

    # Distance to the nearest mapped industrial feature is a property of the
    # PLACE, not of any clustering, so it is computed once up front and then
    # reused by both the sweep and the per-cluster summary.
    osm = pd.read_csv(OSM_FILE)
    print(f"OSM industrial features: {len(osm):,}")
    osm_tree = cKDTree(to_xyz(osm.latitude.values, osm.longitude.values))
    chord, index = osm_tree.query(to_xyz(places.latitude.values,
                                         places.longitude.values))
    places["km_to_osm"] = 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2, 0, 1))
    places["nearest_osm_class"] = osm.osm_class.values[index]
    places["nearest_osm_name"] = osm.name.fillna("").values[index]

    surveyed, batches_done = surveyed_cell_ids()
    places["osm_surveyed"] = places.cell_id.isin(surveyed)
    print(f"OSM batches completed: {batches_done}  ->  "
          f"{int(places.osm_surveyed.sum()):,} of {len(places):,} places "
          f"({places.osm_surveyed.mean():.0%}) have actually been queried")

    # ---- Parameter sweep -------------------------------------------------
    print("\n=== Parameter sweep ===")
    sweep_table = sweep(points_rad, places.km_to_osm.values)
    print(sweep_table.to_string(index=False))
    print(f"\nUsing eps={EPS_KM} km, min_samples={MIN_SAMPLES}\n")

    # ---- The chosen clustering -------------------------------------------
    labels = run_dbscan(points_rad, EPS_KM, MIN_SAMPLES)
    places["cluster"] = labels

    clustered = labels != -1
    cluster_ids = sorted(set(labels[clustered]))
    n_clusters = len(cluster_ids)
    n_noise = int((~clustered).sum())

    sizes = pd.Series(labels[clustered]).value_counts().sort_values(ascending=False)

    print("=== DBSCAN metrics ===")
    print(f"  Total points clustered on : {len(places):,}")
    print(f"  Clusters found            : {n_clusters:,}")
    print(f"  Noise / outlier points    : {n_noise:,}")
    print(f"  Noise percentage          : {100 * n_noise / len(places):.1f}%")
    print(f"  Points in clusters        : {int(clustered.sum()):,} "
          f"({100 * clustered.mean():.1f}%)")
    if n_clusters:
        print(f"  Largest cluster           : {int(sizes.iloc[0]):,} points "
              f"(cluster {sizes.index[0]})")
        print(f"  Smallest cluster          : {int(sizes.iloc[-1]):,} points")
        print(f"  Mean cluster size         : {sizes.mean():.1f}")
        print(f"  Median cluster size       : {sizes.median():.1f}")

    # Silhouette on the clustered points only. Noise has no cluster to be
    # close to, so including it would be meaningless.
    silhouette = None
    if n_clusters >= 2:
        sub = places[clustered]
        if len(sub) > SILHOUETTE_SAMPLE:
            sub = sub.sample(SILHOUETTE_SAMPLE, random_state=42)
        if sub.cluster.nunique() >= 2:
            silhouette = float(silhouette_score(
                np.radians(sub[["latitude", "longitude"]].to_numpy()),
                sub.cluster.values, metric="haversine",
            ))
            print(f"  Silhouette (n={len(sub):,})    : {silhouette:.3f}")

    # ---- Per-cluster table -----------------------------------------------
    print("\n=== Building per-cluster summary ===")
    osm = pd.read_csv(OSM_FILE)
    print(f"OSM industrial features: {len(osm):,}")
    osm_tree = cKDTree(to_xyz(osm.latitude.values, osm.longitude.values))

    # Nearest mapped industrial feature for every place.
    chord, index = osm_tree.query(to_xyz(places.latitude.values,
                                         places.longitude.values))
    places["km_to_osm"] = 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2, 0, 1))
    places["nearest_osm_class"] = osm.osm_class.values[index]
    places["nearest_osm_name"] = osm.name.fillna("").values[index]

    records = []
    for cid in cluster_ids:
        group = places[places.cluster == cid]
        nearest = group.km_to_osm.min()
        matched = bool(nearest <= MATCH_KM)
        # A cluster can only be called a false positive if OSM was actually
        # asked about it. Otherwise the honest verdict is "not checked".
        checked = bool(group.osm_surveyed.any())
        verdict = ("confirmed" if matched
                   else "contradicted" if checked
                   else "unchecked")
        # What kind of industry, judged by the members that actually matched.
        hits = group[group.km_to_osm <= MATCH_KM]
        kinds = hits.nearest_osm_class.value_counts()
        records.append({
            "cluster": int(cid),
            "points": int(len(group)),
            "latitude": float(group.latitude.mean()),
            "longitude": float(group.longitude.mean()),
            "extent_km": round(cluster_extent_km(group), 2),
            "mean_static_probability": round(float(group.static_probability.mean()), 4),
            "mean_night_fraction": round(float(group.night_fraction.mean()), 3),
            "mean_active_days": round(float(group.active_days.mean()), 1),
            "members_matched": int(len(hits)),
            "match_rate": round(len(hits) / len(group), 3),
            "nearest_osm_km": round(float(nearest), 2),
            "dominant_osm_class": kinds.index[0] if len(kinds) else None,
            "nearest_osm_name": str(
                group.loc[group.km_to_osm.idxmin(), "nearest_osm_name"] or ""
            ) or None,
            "near_power_plant": bool(group.near_power_plant.any()),
            "is_volcanic": bool(group.is_volcanic.any()),
            "osm_confirmed": matched,
            "osm_checked": checked,
            "verdict": verdict,
        })

    clusters = pd.DataFrame(records).sort_values("points", ascending=False)

    confirmed = clusters[clusters.verdict == "confirmed"]
    contradicted = clusters[clusters.verdict == "contradicted"]
    unchecked = clusters[clusters.verdict == "unchecked"]
    judged = len(confirmed) + len(contradicted)

    print(f"\n=== OSM validation (match radius {MATCH_KM} km) ===")
    print(f"  Confirmed    - industry mapped within {MATCH_KM} km : "
          f"{len(confirmed):,}")
    print(f"  Contradicted - queried, nothing found there       : "
          f"{len(contradicted):,}")
    print(f"  Unchecked    - OSM fetch has not reached them yet : "
          f"{len(unchecked):,}")
    print(f"\n  Of the {judged:,} clusters actually testable, "
          f"{100 * len(confirmed) / max(judged, 1):.1f}% are confirmed.")
    print(f"  Points inside confirmed clusters: {int(confirmed.points.sum()):,}")
    if len(confirmed):
        print("\n  What the confirmed clusters sit on:")
        print(confirmed.dominant_osm_class.value_counts().to_string())

    print("\n  Strongest matches (largest clusters fully on mapped industry):")
    best = confirmed.sort_values(["match_rate", "points"], ascending=False).head(8)
    for _, r in best.iterrows():
        print(f"    cluster {r.cluster:>4d}  {r.points:>4d} pts  "
              f"{r.latitude:7.3f},{r.longitude:8.3f}  "
              f"{r.match_rate:>5.0%} matched  {r.dominant_osm_class or '-':16s} "
              f"{str(r.nearest_osm_name or '')[:28]}")

    print("\n  Genuine misses (OSM WAS queried here and found nothing):")
    worst = contradicted.sort_values("points", ascending=False).head(8)
    if not len(worst):
        print("    none")
    for _, r in worst.iterrows():
        print(f"    cluster {r.cluster:>4d}  {r.points:>4d} pts  "
              f"{r.latitude:7.3f},{r.longitude:8.3f}  "
              f"nearest OSM {r.nearest_osm_km:>7.1f} km  "
              f"{'VOLCANO' if r.is_volcanic else ''}")

    # ---- Save ------------------------------------------------------------
    CLUSTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    places.to_csv(CLUSTERS_FILE, index=False)
    clusters.to_csv(CLUSTERS_FILE.with_name("dbscan_cluster_summary.csv"),
                    index=False)

    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    METRICS_FILE.write_text(json.dumps({
        "algorithm": "DBSCAN",
        "metric": "haversine (great-circle, eps in km)",
        "clustered_on": (
            f"persistent places, static_probability >= {MIN_STATIC}, "
            "one 0.05 degree cell per point"
        ),
        "parameters": {"eps_km": EPS_KM, "min_samples": MIN_SAMPLES},
        "points": int(len(places)),
        "clusters": int(n_clusters),
        "noise_points": int(n_noise),
        "noise_pct": round(100 * n_noise / len(places), 2),
        "clustered_points": int(clustered.sum()),
        "largest_cluster": int(sizes.iloc[0]) if n_clusters else 0,
        "smallest_cluster": int(sizes.iloc[-1]) if n_clusters else 0,
        "mean_cluster_size": round(float(sizes.mean()), 2) if n_clusters else 0,
        "median_cluster_size": float(sizes.median()) if n_clusters else 0,
        "silhouette": round(silhouette, 4) if silhouette is not None else None,
        "osm_validation": {
            "features_available": int(len(osm)),
            "match_radius_km": MATCH_KM,
            "batches_completed": batches_done,
            "places_surveyed_pct": round(100 * places.osm_surveyed.mean(), 1),
            "clusters_confirmed": int(len(confirmed)),
            "clusters_contradicted": int(len(contradicted)),
            "clusters_unchecked": int(len(unchecked)),
            "confirmed_pct_of_testable": round(
                100 * len(confirmed) / max(judged, 1), 1),
            "by_industry": confirmed.dominant_osm_class.value_counts().to_dict()
            if len(confirmed) else {},
        },
        "sweep": sweep_table.to_dict(orient="records"),
        "cluster_size_distribution": {
            str(k): int(v) for k, v in sizes.head(30).items()
        },
    }, indent=2), encoding="utf-8")

    print(f"\nSaved clusters to: {CLUSTERS_FILE}")
    print(f"Saved metrics to:  {METRICS_FILE}")
    return places, clusters, osm


if __name__ == "__main__":
    main()
