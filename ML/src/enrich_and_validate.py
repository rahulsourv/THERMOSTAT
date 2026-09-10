"""
Bring in data from OUTSIDE NASA, then use it two different ways.

  Volcanoes (Smithsonian GVP)  ->  a FILTER.
      The model finds "persistent static heat". Volcanoes are exactly that,
      but they are natural, not industrial. We flag them so they can be
      separated instead of quietly polluting the alerts.

  Power plants (WRI)  ->  INDEPENDENT VALIDATION.
      Deliberately NOT used as a feature and NOT used as a label. It is the
      only thing here that NASA had no hand in, so it is the only honest way
      to answer the open question:

          is 'active_days' real signal, or is it circular because NASA may
          assign type=2 to places that keep recurring?

      If the model's top places really are power plants, the signal is real.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

SCORES_FILE = Path("data/processed/hotspot_model_scores_2025.csv")
VOLCANO_FILE = Path("data/external/volcanoes.csv")
PLANT_FILE = Path("data/external/power_plants.csv")
OUTPUT_FILE = Path("data/processed/hotspot_scores_enriched.csv")

EARTH_RADIUS_KM = 6371.0
VOLCANO_RADIUS_KM = 10.0     # within this, treat as a natural source
PLANT_RADIUS_KM = 2.0        # within this, counts as a confirmed match

# Fuels that actually burn something and so can show up on a thermal sensor.
THERMAL_FUELS = {
    "Coal", "Gas", "Oil", "Petcoke", "Biomass", "Waste", "Cogeneration",
}


def to_xyz(lat, lon):
    """Lat/lon degrees -> 3D points on a unit sphere, so a KD-tree can
    measure real distances instead of pretending the Earth is flat."""
    lat_r, lon_r = np.radians(lat), np.radians(lon)
    return np.column_stack([
        np.cos(lat_r) * np.cos(lon_r),
        np.cos(lat_r) * np.sin(lon_r),
        np.sin(lat_r),
    ])


def nearest_km(from_lat, from_lon, to_lat, to_lon):
    tree = cKDTree(to_xyz(to_lat, to_lon))
    chord, _ = tree.query(to_xyz(from_lat, from_lon), k=1)
    # chord length on a unit sphere -> great-circle distance in km
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2, 0, 1))


hs = pd.read_csv(SCORES_FILE)
print(f"Hotspots scored: {len(hs):,}")

# ---- Volcanoes ------------------------------------------------------------
volc = pd.read_csv(VOLCANO_FILE)
volc = volc.dropna(subset=["Latitude", "Longitude"])
print(f"Volcanoes loaded: {len(volc):,}")

hs["km_to_volcano"] = nearest_km(
    hs["latitude"].values, hs["longitude"].values,
    volc["Latitude"].values, volc["Longitude"].values,
)
hs["is_volcanic"] = hs["km_to_volcano"] <= VOLCANO_RADIUS_KM

# ---- Power plants ---------------------------------------------------------
plants = pd.read_csv(PLANT_FILE, usecols=[
    "name", "capacity_mw", "latitude", "longitude", "primary_fuel",
])
plants = plants.dropna(subset=["latitude", "longitude"])
thermal = plants[plants["primary_fuel"].isin(THERMAL_FUELS)]
print(f"Power plants loaded: {len(plants):,}  ->  thermal only: {len(thermal):,}")

hs["km_to_thermal_plant"] = nearest_km(
    hs["latitude"].values, hs["longitude"].values,
    thermal["latitude"].values, thermal["longitude"].values,
)
hs["near_power_plant"] = hs["km_to_thermal_plant"] <= PLANT_RADIUS_KM

hs.to_csv(OUTPUT_FILE, index=False)

# ==========================================================================
# VALIDATION - the part that actually settles the question
# ==========================================================================
print("\n" + "=" * 72)
print("INDEPENDENT VALIDATION against WRI power plants")
print("(this dataset was never a feature and never a label)")
print("=" * 72)

base_rate = hs["near_power_plant"].mean()
print(f"\nBase rate: {base_rate:.4%} of all {len(hs):,} places sit within "
      f"{PLANT_RADIUS_KM:.0f} km of a thermal power plant.")
print("This is what pure chance would give us.\n")

# Exclude volcanoes: we are asking about HUMAN-MADE sources.
human = hs[~hs["is_volcanic"]].copy()

rankings = {
    "ML model (out-of-fold)": human["static_probability"],
    "active_days alone": human["active_days"],
    "night_fraction alone": human["night_fraction"],
    "NASA type2_fraction": human["type2_fraction"],
}

truth = human["near_power_plant"].values


def top_k_rate(values, k, repeats=200, seed=0):
    """Hit rate in the top k, with TIES BROKEN AT RANDOM.

    Without this, night_fraction (about 15,000 places tied at exactly 1.0)
    gets ordered by however the file happens to be sorted, which can invent
    a result that is not real. Returns mean and spread over random draws.
    """
    rng = np.random.default_rng(seed)
    v = np.asarray(values, dtype=float)
    out = [
        truth[np.lexsort((rng.random(len(v)), -v))[:k]].mean()
        for _ in range(repeats)
    ]
    return float(np.mean(out)), float(np.std(out))


print(f"{'ranking method':26s} {'top100':>8s} {'top500':>8s} "
      f"{'top2000':>8s} {'lift@500':>9s} {'stability':>10s}")
print("-" * 78)

for name, score in rankings.items():
    p100, _ = top_k_rate(score.values, 100)
    p500, sd500 = top_k_rate(score.values, 500)
    p2000, _ = top_k_rate(score.values, 2000)
    lift = p500 / base_rate if base_rate else float("nan")
    flag = "stable" if sd500 < 0.005 else f"+/-{sd500:.1%} !"
    print(f"{name:26s} {p100:7.1%} {p500:7.1%} {p2000:7.1%} "
          f"{lift:8.1f}x {flag:>10s}")

# Threshold view: robust to the large group of places tied near p=0.997.
print("\nSame question, by confidence band (avoids arbitrary top-N ties):")
print(f"{'band':26s} {'places':>9s} {'near plant':>11s} {'lift':>7s}")
print("-" * 56)
for lo, hi in [(0.99, 1.01), (0.90, 0.99), (0.50, 0.90), (0.0, 0.50)]:
    band = human[
        (human["static_probability"] >= lo) & (human["static_probability"] < hi)
    ]
    if len(band) == 0:
        continue
    rate = band["near_power_plant"].mean()
    print(f"p {lo:.2f} - {hi:.2f}{'':13s}"[:26]
          + f" {len(band):9,} {rate:10.1%} {rate / base_rate:6.1f}x")

# ---- Volcano contamination ------------------------------------------------
# Use a probability THRESHOLD, not top-N. Thousands of places are tied in a
# very narrow band near 0.997, so "top 500" would just be an arbitrary slice
# of that tie and would miss real contamination sitting just below it.
print("\n" + "=" * 72)
print("VOLCANO CONTAMINATION among confident predictions")
print("=" * 72)
confident = hs[hs["static_probability"] >= 0.90]
n_volc = int(confident["is_volcanic"].sum())
print(f"\nPlaces with probability >= 0.90: {len(confident):,}")
print(f"Of these, {n_volc} sit within {VOLCANO_RADIUS_KM:.0f} km of a volcano "
      f"({n_volc / max(len(confident), 1):.2%}) - now flagged as natural.")
if n_volc:
    named = confident[confident["is_volcanic"]].nlargest(6, "static_probability")
    print("\nExamples now correctly flagged as natural:")
    for _, r in named.iterrows():
        v = volc.iloc[
            int(np.argmin(
                (volc["Latitude"] - r["latitude"]) ** 2
                + (volc["Longitude"] - r["longitude"]) ** 2
            ))
        ]
        print(f"  {r['latitude']:8.3f},{r['longitude']:9.3f}  "
              f"p={r['static_probability']:.3f}  "
              f"{v['Volcano_Name']} ({v['Country']})")

print(f"\nSaved enriched scores to: {OUTPUT_FILE}")
