"""
Inspect the Global Industrial Heat Source (IHS) dataset and score its use to us.

Ma et al., "Global High-Energy-Consuming Industry Heat Source Dataset v3.0"
(2023-08-16), 25,544 objects built from NPP-VIIRS 375 m active fire data
2012-2021, verified against POI records and high-resolution imagery.

THE FIELD THAT MATTERS, AND WHAT IT IS NOT

  The readme defines `Type` as:
      0 = verified as an industrial heat source
      1 = NOT an industrial heat source
      2 = uncertain
  and the shapefile lineage confirms it: `CalculateField Type [if_industr]`.

  So this is an IS-INDUSTRIAL flag, not an industry taxonomy. There is no
  field anywhere in the dataset that says flare vs refinery vs kiln. That
  single fact decides what it can and cannot fix for us, so this script
  checks for such a field rather than assuming one is absent.

READ ONLY. Writes a CSV extract and a JSON report; touches nothing in the
training pipeline and overwrites no model.
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import shapefile
from scipy.spatial import cKDTree

IHS_DIR = Path("data/external/industrial_heat_sources")
PLACES_FILE = Path("data/processed/hotspot_scores_enriched.csv")
OSM_FILE = Path("data/external/osm_features.csv")
PLANT_FILE = Path("data/external/power_plants.csv")
VOLCANO_FILE = Path("data/external/volcanoes.csv")

OUT_CSV = Path("data/processed/ihs_points.csv")
OUT_JSON = Path("models/ihs_assessment.json")

EARTH_RADIUS_KM = 6371.0

# The readme's codebook, not a guess.
TYPE_MEANING = {
    0: "verified industrial heat source",
    1: "verified NOT an industrial heat source",
    2: "uncertain",
}

# Radii reused from the existing pipeline so the numbers are comparable.
OSM_MATCH_KM = 3.0
PLANT_MATCH_KM = 2.0
VOLCANO_MATCH_KM = 10.0
# Our cells are 0.05 deg (~5.6 km); half a diagonal is ~4 km, so this is the
# distance inside which an IHS object and one of our cells are the same place.
CELL_MATCH_KM = 4.0

YEAR_COLS = [f"date{y}_p" for y in range(2012, 2022)]


def to_xyz(lat, lon):
    lat_r, lon_r = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    return np.column_stack([
        np.cos(lat_r) * np.cos(lon_r),
        np.cos(lat_r) * np.sin(lon_r),
        np.sin(lat_r),
    ])


def nearest_km(from_lat, from_lon, to_lat, to_lon):
    """Great-circle distance to the nearest target, in km, plus its index."""
    tree = cKDTree(to_xyz(to_lat, to_lon))
    chord, idx = tree.query(to_xyz(from_lat, from_lon))
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2, 0, 1)), idx


def load_points() -> pd.DataFrame:
    shp = [p for p in glob.glob(str(IHS_DIR / "**/*.shp"), recursive=True)
           if "（点）" in p or "point" in p.lower()]
    if not shp:                       # fall back to whichever is POINT type
        shp = glob.glob(str(IHS_DIR / "**/*.shp"), recursive=True)
    reader = None
    for path in shp:
        r = shapefile.Reader(path, encoding="utf-8")
        if r.shapeTypeName == "POINT":
            reader, chosen = r, path
            break
    if reader is None:
        raise SystemExit("No POINT shapefile found under " + str(IHS_DIR))

    print(f"Reading: {Path(chosen).name}")
    fields = [f[0] for f in reader.fields[1:]]
    rows = reader.records()
    df = pd.DataFrame(rows, columns=fields)
    coords = np.array([s.points[0] for s in reader.shapes()])
    df["longitude"] = coords[:, 0]
    df["latitude"] = coords[:, 1]
    return df, fields


def valid_date(value: str):
    """The Max_date column contains real corruption ('0202-10-31')."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return None
    year = int(value[:4])
    return value if 2012 <= year <= 2022 else None


def main():
    df, fields = load_points()
    n = len(df)
    print(f"Records: {n:,}\n")

    report = {
        "dataset": "Global High-Energy-Consuming Industry Heat Source v3.0 (Ma et al., 2023-08-16)",
        "source_sensor": "NPP-VIIRS 375 m active fire, 2012-01-20 to 2021-12-31",
        "crs": "WGS84 geographic (EPSG:4326) - same as ThermoStats, no reprojection needed",
        "total_records": int(n),
        "fields": fields,
    }

    # ---- 1. Is there ANY industry-type field? ----------------------------
    type_like = [f for f in fields
                 if re.search(r"type|class|categ|industry|sector|kind", f, re.I)]
    report["industry_type_fields_found"] = type_like
    print("Fields that could carry an industry taxonomy:", type_like)
    for f in type_like:
        vals = df[f].unique()
        print(f"  {f}: {len(vals)} distinct -> {sorted(vals)[:12]}")

    # ---- 2. Class balance -------------------------------------------------
    counts = df.Type.value_counts().sort_index()
    report["records_per_class"] = {
        str(int(k)): {"n": int(v), "meaning": TYPE_MEANING.get(int(k), "?")}
        for k, v in counts.items()
    }
    print("\n=== Type (the readme's codebook) ===")
    for k, v in counts.items():
        print(f"  {int(k)} = {TYPE_MEANING.get(int(k),'?'):<40} {v:>7,}  ({v/n:.1%})")

    # ---- 3. Coordinate validity ------------------------------------------
    bad_coord = (
        df.latitude.isna() | df.longitude.isna()
        | (df.latitude.abs() > 90) | (df.longitude.abs() > 180)
        | ((df.latitude == 0) & (df.longitude == 0))
    )
    report["invalid_coordinates"] = int(bad_coord.sum())
    print(f"\nInvalid coordinates: {int(bad_coord.sum())}")

    # ---- 4. Duplicates ----------------------------------------------------
    exact = df.duplicated(subset=["latitude", "longitude"]).sum()
    rounded = df.duplicated(subset=[df.latitude.round(4).name]) if False else None
    key = df.latitude.round(4).astype(str) + "," + df.longitude.round(4).astype(str)
    near_dupe = int(key.duplicated().sum())
    report["duplicates"] = {"exact_coordinate": int(exact),
                            "same_to_4dp_about_11m": near_dupe}
    print(f"Duplicate coordinates: exact {int(exact)}, to ~11 m {near_dupe}")

    # ---- 5. Time coverage --------------------------------------------------
    min_ok = df.Min_date.map(valid_date)
    max_ok = df.Max_date.map(valid_date)
    report["time_coverage"] = {
        "declared": "2012-01-20 to 2021-12-31",
        "min_date_valid": int(min_ok.notna().sum()),
        "min_date_corrupt_or_blank": int(min_ok.isna().sum()),
        "max_date_valid": int(max_ok.notna().sum()),
        "max_date_corrupt_or_blank": int(max_ok.isna().sum()),
        "example_corrupt": sorted(
            {v for v in df.Max_date if isinstance(v, str) and valid_date(v) is None and v.strip()}
        )[:6],
    }
    print(f"\nMin_date usable {int(min_ok.notna().sum()):,} / corrupt-or-blank "
          f"{int(min_ok.isna().sum()):,}")
    print(f"Max_date usable {int(max_ok.notna().sum()):,} / corrupt-or-blank "
          f"{int(max_ok.isna().sum()):,}")
    print("  corrupt examples:", report["time_coverage"]["example_corrupt"])

    years = {c: int((df[c] > 0).sum()) for c in YEAR_COLS if c in df}
    report["objects_active_per_year"] = years
    print("\nObjects with at least one fire point, per year:")
    for c, v in years.items():
        print(f"  {c[4:8]}  {v:>7,}  {'#' * int(v / 400)}")

    # ---- 6. Geography ------------------------------------------------------
    report["geographic_coverage"] = {
        "bbox": [float(df.longitude.min()), float(df.latitude.min()),
                 float(df.longitude.max()), float(df.latitude.max())],
        "by_continent": df.CONTINENT.replace("", "(unassigned)").value_counts().to_dict(),
        "top_nations": df.Nation.replace("", "(unassigned)").value_counts().head(15).to_dict(),
    }
    india = df[(df.latitude.between(6, 36)) & (df.longitude.between(68, 98))]
    report["india_records"] = int(len(india))
    report["india_verified_ihs"] = int((india.Type == 0).sum())
    print(f"\nIndia bbox: {len(india):,} objects, "
          f"{int((india.Type==0).sum()):,} verified industrial")

    # ---- 7. Overlap with OUR reference places ------------------------------
    places = pd.read_csv(
        PLACES_FILE,
        usecols=["cell_id", "latitude", "longitude", "static_probability",
                 "event_class", "class_source"],
    )
    km_to_place, place_idx = nearest_km(df.latitude, df.longitude,
                                        places.latitude, places.longitude)
    df["km_to_our_place"] = km_to_place
    df["our_cell_id"] = places.cell_id.values[place_idx]
    df["our_static_probability"] = places.static_probability.values[place_idx]
    matched = df.km_to_our_place <= CELL_MATCH_KM
    report["overlap_with_thermostats"] = {
        "match_radius_km": CELL_MATCH_KM,
        "ihs_matching_one_of_our_cells": int(matched.sum()),
        "ihs_with_no_cell_within_radius": int((~matched).sum()),
        "distinct_cells_touched": int(df.loc[matched, "our_cell_id"].nunique()),
    }
    print(f"\nIHS objects landing on one of our 687,289 cells "
          f"(<= {CELL_MATCH_KM} km): {int(matched.sum()):,} "
          f"({matched.mean():.1%})")

    # How our stage-1 model scored the places the IHS authors verified.
    verified = df[(df.Type == 0) & matched]
    negatives = df[(df.Type == 1) & matched]
    report["agreement_with_stage1"] = {
        "verified_ihs_matched": int(len(verified)),
        "of_those_our_p_ge_0.9": int((verified.our_static_probability >= 0.9).sum()),
        "of_those_our_p_lt_0.5": int((verified.our_static_probability < 0.5).sum()),
        "verified_non_ihs_matched": int(len(negatives)),
        "non_ihs_our_p_ge_0.9": int((negatives.our_static_probability >= 0.9).sum()),
    }
    if len(verified):
        print(f"\nOf {len(verified):,} VERIFIED industrial sources on our cells:")
        print(f"  our model already scores >= 0.90 : "
              f"{int((verified.our_static_probability>=0.9).sum()):,} "
              f"({(verified.our_static_probability>=0.9).mean():.1%})")
        print(f"  our model scores  < 0.50 (missed): "
              f"{int((verified.our_static_probability<0.5).sum()):,} "
              f"({(verified.our_static_probability<0.5).mean():.1%})")
    if len(negatives):
        print(f"Of {len(negatives):,} verified NON-industrial on our cells, "
              f"we wrongly score {int((negatives.our_static_probability>=0.9).sum()):,} "
              f"at >= 0.90")

    # ---- 8. Leakage against the labels we already train on ------------------
    osm = pd.read_csv(OSM_FILE)
    km_osm, osm_idx = nearest_km(df.latitude, df.longitude,
                                 osm.latitude, osm.longitude)
    plants = pd.read_csv(PLANT_FILE, low_memory=False)
    plants = plants.dropna(subset=["latitude", "longitude"])
    km_plant, _ = nearest_km(df.latitude, df.longitude,
                             plants.latitude, plants.longitude)
    volc = pd.read_csv(VOLCANO_FILE)
    vlat = next(c for c in volc.columns if "lat" in c.lower())
    vlon = next(c for c in volc.columns if "lon" in c.lower())
    volc = volc.dropna(subset=[vlat, vlon])
    km_volc, _ = nearest_km(df.latitude, df.longitude, volc[vlat], volc[vlon])

    df["km_to_osm"] = km_osm
    df["nearest_osm_class"] = osm.osm_class.values[osm_idx]
    df["km_to_plant"] = km_plant
    df["km_to_volcano"] = km_volc

    overlap_osm = int((km_osm <= OSM_MATCH_KM).sum())
    overlap_plant = int((km_plant <= PLANT_MATCH_KM).sum())
    overlap_volc = int((km_volc <= VOLCANO_MATCH_KM).sum())
    fresh = int(((km_osm > OSM_MATCH_KM) & (km_plant > PLANT_MATCH_KM)).sum())
    report["label_leakage"] = {
        "within_3km_of_an_osm_feature": overlap_osm,
        "within_2km_of_a_wri_plant": overlap_plant,
        "within_10km_of_a_volcano": overlap_volc,
        "independent_of_both_osm_and_wri": fresh,
        "note": (
            "Objects overlapping OSM/WRI are NOT new evidence - our stage-2 "
            "model already trains on those exact labels, so scoring against "
            "them would be marking our own homework. The independent subset "
            "is the honest evaluation set."
        ),
    }
    print(f"\n=== Leakage against labels we already use ===")
    print(f"  within {OSM_MATCH_KM} km of an OSM feature : {overlap_osm:,} ({overlap_osm/n:.1%})")
    print(f"  within {PLANT_MATCH_KM} km of a WRI plant   : {overlap_plant:,} ({overlap_plant/n:.1%})")
    print(f"  within {VOLCANO_MATCH_KM} km of a volcano   : {overlap_volc:,} ({overlap_volc/n:.1%})")
    print(f"  INDEPENDENT of both OSM and WRI  : {fresh:,} ({fresh/n:.1%})")

    # ---- 9. Usable / unusable ----------------------------------------------
    usable_stage1 = int(((df.Type.isin([0, 1])) & (~bad_coord)).sum())
    report["usability"] = {
        "stage1_persistent_source_detection": {
            "usable_records": usable_stage1,
            "positives": int((df.Type == 0).sum()),
            "negatives": int((df.Type == 1).sum()),
            "verdict": "STRONG - verified positives and, rarer and more valuable, verified negatives",
        },
        "stage2a_industrial_vs_natural": {
            "usable_records": int((df.Type == 1).sum()),
            "verdict": "STRONG - the 'not industrial' class is exactly the negative we lack",
        },
        "stage2b_exact_industry": {
            "usable_records": 0,
            "verdict": "NONE - the dataset carries no industry-type field at all",
        },
        "unusable": {
            "uncertain_type_2": int((df.Type == 2).sum()),
            "invalid_coordinates": int(bad_coord.sum()),
            "corrupt_max_date": int(max_ok.isna().sum()),
        },
    }

    # ---- 10. Save -----------------------------------------------------------
    keep = ["latitude", "longitude", "Type", "Points_num", "Min_date", "Max_date",
            "CONTINENT", "Nation", "area", "km_to_our_place", "our_cell_id",
            "our_static_probability", "km_to_osm", "nearest_osm_class",
            "km_to_plant", "km_to_volcano"] + [c for c in YEAR_COLS if c in df]
    out = df[keep].copy()
    out["type_meaning"] = out.Type.map(TYPE_MEANING)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved extract to: {OUT_CSV}")
    print(f"Saved report to:  {OUT_JSON}")


if __name__ == "__main__":
    main()
