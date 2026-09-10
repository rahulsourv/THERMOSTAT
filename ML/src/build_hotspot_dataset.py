"""
Build a PLACE-level dataset from the 2025 archive.

One row = one 0.05 degree cell (about 5 km), not one satellite detection.

Why: a single detection cannot tell us whether a place is a persistent
industrial heat source. A year of behaviour at that place can.

Includes BOTH classes, so the data is actually trainable:
  label  1 = cell where nearly all detections are FIRMS type 2 (static source)
  label  0 = cell where nearly all detections are FIRMS type 0 (vegetation fire)
  label -1 = mixed cells, kept in the file but excluded from training
"""

from pathlib import Path

import numpy as np
import pandas as pd

INPUT_FILE = Path("data/processed/archive_2025_noaa20_clean.csv")
OUTPUT_FILE = Path("data/processed/hotspot_features_2025.csv")

GRID_SIZE = 0.05
CHUNK_SIZE = 2_000_000
MIN_DETECTIONS = 4          # ignore cells seen only once or twice
LAT_OFFSET, LON_OFFSET = 2000, 4000

USECOLS = [
    "latitude", "longitude", "detected_at_utc",
    "bright_ti4", "bright_ti5", "frp", "daynight", "fire_type",
]
DTYPES = {
    "latitude": "float32", "longitude": "float32",
    "bright_ti4": "float32", "bright_ti5": "float32", "frp": "float32",
    "daynight": "string", "fire_type": "float32",
}

# date_key (month*100 + day) -> day of year, for the 2025 calendar
_dates = pd.date_range("2025-01-01", "2025-12-31")
DOY_LOOKUP = pd.Series(
    _dates.dayofyear.values,
    index=(_dates.month * 100 + _dates.day).values,
)

stat_parts, day_parts, month_parts = [], [], []
rows_read = 0

print("Building place-level hotspots from the 2025 archive...")

reader = pd.read_csv(
    INPUT_FILE, usecols=USECOLS, dtype=DTYPES, chunksize=CHUNK_SIZE
)

for chunk_number, chunk in enumerate(reader, start=1):
    rows_read += len(chunk)

    # Keep only the two classes we can label.
    chunk = chunk[chunk["fire_type"].isin([0, 2])]
    if chunk.empty:
        continue

    # Cheap date handling: slice the string instead of parsing 18M timestamps.
    stamp = chunk["detected_at_utc"].str
    month = stamp[5:7].astype("int16")
    day = stamp[8:10].astype("int16")
    date_key = (month * 100 + day).astype("int32")

    lat_cell = np.floor(chunk["latitude"] / GRID_SIZE).astype("int32")
    lon_cell = np.floor(chunk["longitude"] / GRID_SIZE).astype("int32")
    cell_id = (
        (lat_cell + LAT_OFFSET) * 10000 + (lon_cell + LON_OFFSET)
    ).astype("int64")

    work = pd.DataFrame({
        "cell_id": cell_id.values,
        "lat": chunk["latitude"].values,
        "lon": chunk["longitude"].values,
        "frp": chunk["frp"].values,
        "ti4": chunk["bright_ti4"].values,
        "ti5": chunk["bright_ti5"].values,
        "is_night": (chunk["daynight"].values == "N").astype("int8"),
        "is_type2": (chunk["fire_type"].values == 2).astype("int8"),
        "date_key": date_key.values,
        "month": month.values,
    })

    # Sums and sums-of-squares let us combine chunks and still get exact
    # means and standard deviations at the end.
    work["frp_sq"] = work["frp"] ** 2
    work["ti4_sq"] = work["ti4"] ** 2
    work["lat_sq"] = work["lat"] ** 2
    work["lon_sq"] = work["lon"] ** 2
    work["ti4_minus_ti5"] = work["ti4"] - work["ti5"]

    stat_parts.append(
        work.groupby("cell_id").agg(
            n=("frp", "size"),
            sum_frp=("frp", "sum"), sum_frp_sq=("frp_sq", "sum"),
            max_frp=("frp", "max"),
            sum_ti4=("ti4", "sum"), sum_ti4_sq=("ti4_sq", "sum"),
            sum_ti5=("ti5", "sum"), sum_diff=("ti4_minus_ti5", "sum"),
            sum_night=("is_night", "sum"), sum_type2=("is_type2", "sum"),
            sum_lat=("lat", "sum"), sum_lat_sq=("lat_sq", "sum"),
            sum_lon=("lon", "sum"), sum_lon_sq=("lon_sq", "sum"),
        )
    )
    day_parts.append(work[["cell_id", "date_key"]].drop_duplicates())
    month_parts.append(work[["cell_id", "month"]].drop_duplicates())

    print(f"  chunk {chunk_number}: {rows_read:,} rows read")

print("\nCombining chunks...")

all_stats = pd.concat(stat_parts)
stats = all_stats.groupby(level=0).sum()
stats["max_frp"] = all_stats.groupby(level=0)["max_frp"].max()
del all_stats, stat_parts

stats = stats[stats["n"] >= MIN_DETECTIONS]

days = pd.concat(day_parts).drop_duplicates()
days = days[days["cell_id"].isin(stats.index)]
months = pd.concat(month_parts).drop_duplicates()
months = months[months["cell_id"].isin(stats.index)]
del day_parts, month_parts

print(f"Cells kept (>= {MIN_DETECTIONS} detections): {len(stats):,}")

# ---- A. Persistence -------------------------------------------------------
days["doy"] = days["date_key"].map(DOY_LOOKUP).astype("int16")
days = days.sort_values(["cell_id", "doy"])

per_day = days.groupby("cell_id")["doy"]
persistence = pd.DataFrame({
    "active_days": per_day.nunique(),
    "first_doy": per_day.min(),
    "last_doy": per_day.max(),
})
# Longest silent stretch between two consecutive active days.
days["gap"] = days.groupby("cell_id")["doy"].diff()
persistence["longest_gap_days"] = (
    days.groupby("cell_id")["gap"].max().fillna(0)
)

persistence["span_days"] = (
    persistence["last_doy"] - persistence["first_doy"] + 1
)
persistence["duty_cycle"] = (
    persistence["active_days"] / persistence["span_days"]
)

# ---- Seasonality ----------------------------------------------------------
days["m"] = days["date_key"] // 100
monthly = days.groupby(["cell_id", "m"]).size().rename("cnt").reset_index()
season = monthly.groupby("cell_id")["cnt"].agg(["std", "mean", "max", "sum"])
seasonality = pd.DataFrame({
    "months_active": months.groupby("cell_id")["month"].nunique(),
    # spread of activity across months, scale-free: low = steady all year
    "month_cv": (season["std"] / season["mean"]).fillna(0),
    # share of all activity falling in its single busiest month
    "peak_month_share": season["max"] / season["sum"],
})

# ---- B, C. Night + thermal ------------------------------------------------
n = stats["n"]
out = pd.DataFrame(index=stats.index)
out["total_detections"] = n
out["night_fraction"] = stats["sum_night"] / n

out["frp_mean"] = stats["sum_frp"] / n
out["frp_max"] = stats["max_frp"]
frp_var = (stats["sum_frp_sq"] / n - out["frp_mean"] ** 2).clip(lower=0)
out["frp_std"] = np.sqrt(frp_var)
out["frp_cv"] = out["frp_std"] / out["frp_mean"].replace(0, np.nan)

out["ti4_mean"] = stats["sum_ti4"] / n
ti4_var = (stats["sum_ti4_sq"] / n - out["ti4_mean"] ** 2).clip(lower=0)
out["ti4_std"] = np.sqrt(ti4_var)
out["ti5_mean"] = stats["sum_ti5"] / n
out["ti4_minus_ti5_mean"] = stats["sum_diff"] / n

# ---- D. Spatial tightness -------------------------------------------------
mean_lat = stats["sum_lat"] / n
mean_lon = stats["sum_lon"] / n
lat_sd = np.sqrt((stats["sum_lat_sq"] / n - mean_lat ** 2).clip(lower=0))
lon_sd = np.sqrt((stats["sum_lon_sq"] / n - mean_lon ** 2).clip(lower=0))
# Convert degrees to km so the number means the same thing everywhere.
out["spread_km"] = np.sqrt(
    (lat_sd * 111.0) ** 2
    + (lon_sd * 111.0 * np.cos(np.radians(mean_lat))) ** 2
)

out = out.join(persistence).join(seasonality)
out["latitude"] = mean_lat
out["longitude"] = mean_lon

# ---- Neighbour isolation --------------------------------------------------
lat_cell = (out.index // 10000) - LAT_OFFSET
lon_cell = (out.index % 10000) - LON_OFFSET
present = set(zip(lat_cell.values, lon_cell.values))
out["active_neighbours"] = [
    sum(
        (la + dla, lo + dlo) in present
        for dla in (-1, 0, 1) for dlo in (-1, 0, 1)
        if not (dla == 0 and dlo == 0)
    )
    for la, lo in zip(lat_cell.values, lon_cell.values)
]

# ---- Label ----------------------------------------------------------------
out["type2_fraction"] = stats["sum_type2"] / n
out["label"] = np.where(
    out["type2_fraction"] >= 0.8, 1,
    np.where(out["type2_fraction"] <= 0.2, 0, -1),
)

out = out.reset_index(names="cell_id")
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(OUTPUT_FILE, index=False)

counts = out["label"].value_counts()
print(f"\nHotspots built: {len(out):,}")
print(f"  label  1 (static-like):     {counts.get(1, 0):,}")
print(f"  label  0 (vegetation-like): {counts.get(0, 0):,}")
print(f"  label -1 (mixed, excluded): {counts.get(-1, 0):,}")
print(f"\nSaved to: {OUTPUT_FILE}")
