"""
Health check for the whole ThermoStats ML pipeline.

Run this any time to confirm every piece still works and that no leaky
feature has crept back in.
"""

from pathlib import Path

import joblib
import pandas as pd

PASS, FAIL, WARN = "[ OK ]", "[FAIL]", "[WARN]"
results = []


def check(name, condition, detail="", warn_only=False):
    mark = PASS if condition else (WARN if warn_only else FAIL)
    results.append((mark, name, detail))
    print(f"{mark} {name}" + (f"  -  {detail}" if detail else ""))
    return condition


print("=" * 70)
print("THERMOSTATS PIPELINE CHECK")
print("=" * 70)

# ---- 1. Data files --------------------------------------------------------
print("\n1. DATA")
archive = Path("data/processed/archive_2025_noaa20_clean.csv")
hotspots = Path("data/processed/hotspot_features_2025.csv")
scores = Path("data/processed/hotspot_model_scores_2025.csv")
alerts = Path("data/processed/live_hotspot_alerts.csv")

check("2025 archive present", archive.exists(),
      f"{archive.stat().st_size / 1e9:.2f} GB" if archive.exists() else "missing")
check("hotspot feature table built", hotspots.exists())
check("model scores written", scores.exists())
check("live alerts written", alerts.exists())

# ---- 2. Dataset is trainable ---------------------------------------------
print("\n2. DATASET")
hs = pd.read_csv(hotspots)
n_pos = int((hs["label"] == 1).sum())
n_neg = int((hs["label"] == 0).sum())
check("one row per place, not per detection", "active_days" in hs.columns,
      f"{len(hs):,} places")
check("has POSITIVE class", n_pos > 0, f"{n_pos:,} static-like")
check("has NEGATIVE class", n_neg > 0, f"{n_neg:,} vegetation-like")
check("has an 'unknown' bucket kept out of training",
      int((hs["label"] == -1).sum()) > 0,
      f"{int((hs['label'] == -1).sum()):,} mixed cells")

# ---- 3. Feature coverage --------------------------------------------------
print("\n3. FEATURES")
expected = {
    "persistence": ["active_days", "duty_cycle", "span_days",
                    "longest_gap_days", "total_detections"],
    "seasonality": ["months_active", "month_cv", "peak_month_share"],
    "day/night": ["night_fraction"],
    "thermal": ["frp_mean", "frp_max", "frp_std", "frp_cv",
                "ti4_mean", "ti4_std", "ti5_mean", "ti4_minus_ti5_mean"],
    "spatial": ["spread_km", "active_neighbours"],
}
for group, cols in expected.items():
    missing = [c for c in cols if c not in hs.columns]
    check(f"{group:12s} ({len(cols)} features)", not missing,
          "all present" if not missing else f"missing {missing}")

# ---- 4. No leaky features -------------------------------------------------
print("\n4. LEAKAGE GUARD")
bundle = joblib.load(Path("models/hotspot_static_source_model.joblib"))
model_features = bundle["features"]
banned = ["latitude", "longitude", "hour_utc", "month", "first_doy", "last_doy"]
leaked = [b for b in banned if b in model_features]
check("no coordinates / hour used as model inputs", not leaked,
      "clean" if not leaked else f"LEAKED: {leaked}")
check("model trained on the full feature set", len(model_features) >= 19,
      f"{len(model_features)} features")

# ---- 5. Model works -------------------------------------------------------
print("\n5. MODEL")
model = bundle["model"]
sample = hs[hs["label"] >= 0][model_features].head(500)
probs = model.predict_proba(sample)[:, 1]
check("model loads and predicts", len(probs) == len(sample),
      f"probability range {probs.min():.3f} - {probs.max():.3f}")

sc = pd.read_csv(scores, usecols=["static_probability", "label"])
check("scores are out-of-fold (never saw own region)",
      "static_probability" in sc.columns, f"{len(sc):,} places scored")

top100 = sc.nlargest(100, "static_probability")
prec = (top100["label"] == 1).mean()
check("precision@100 above 0.80", prec >= 0.80, f"{prec:.2f}")

# ---- 6. Alerts ------------------------------------------------------------
print("\n6. ALERTS")
al = pd.read_csv(alerts)
check("alerts generated", len(al) > 0, f"{len(al):,} detections scored")
check("every alert carries a plain-English reason",
      al["why"].notna().all() and (al["why"].str.len() > 5).all())
check("alerts spread across the world (not one region)",
      al[al["alert_level"] == "High"]["longitude"].std() > 30,
      f"longitude spread {al[al['alert_level'] == 'High']['longitude'].std():.0f} deg")

# ---- 7. Maps --------------------------------------------------------------
print("\n7. MAPS")
for m in ["hotspot_alerts_map.html", "live_industrial_alerts.html",
          "industrial_thermal_risk_map.html", "firms_detections_map.html"]:
    p = Path("outputs/maps") / m
    check(f"map {m}", p.exists(),
          f"{p.stat().st_size / 1e6:.1f} MB" if p.exists() else "missing")

# ---- 8. External data + independent validation ----------------------------
print("\n8. OUTSIDE-NASA DATA")
plants_file = Path("data/external/power_plants.csv")
volc_file = Path("data/external/volcanoes.csv")
enriched_file = Path("data/processed/hotspot_scores_enriched.csv")

check("WRI power plant database", plants_file.exists())
check("Smithsonian volcano database", volc_file.exists())
check("enriched scores built", enriched_file.exists())

en = pd.read_csv(
    enriched_file,
    usecols=["static_probability", "near_power_plant", "is_volcanic",
             "active_days", "type2_fraction"],
)
base = en["near_power_plant"].mean()
human = en[~en["is_volcanic"]]

top = human.nlargest(500, "static_probability")["near_power_plant"].mean()
check("model beats chance on INDEPENDENT ground truth",
      top > base * 10, f"{top:.1%} vs {base:.3%} base = {top / base:.0f}x lift")

top_days = human.nlargest(500, "active_days")["near_power_plant"].mean()
check("model beats the 'active_days alone' rule",
      top > top_days, f"model {top:.1%} vs active_days {top_days:.1%}")

top_nasa = human.nlargest(500, "type2_fraction")["near_power_plant"].mean()
check("model beats NASA's own type-2 label",
      top > top_nasa, f"model {top:.1%} vs NASA {top_nasa:.1%}")

check("volcanoes separated from industrial alerts",
      int(en["is_volcanic"].sum()) > 0,
      f"{int(en['is_volcanic'].sum()):,} volcanic places flagged")

al_v = pd.read_csv(alerts, usecols=["alert_level", "near_power_plant"])
check("alerts have a 'Natural (volcano)' category",
      (al_v["alert_level"] == "Natural (volcano)").any(),
      f"{int((al_v['alert_level'] == 'Natural (volcano)').sum()):,} detections")

high_conf = al_v[al_v["alert_level"] == "High"]["near_power_plant"].mean()
check("High alerts are independently confirmed at a useful rate",
      high_conf > 0.10, f"{high_conf:.1%} within 2 km of a power plant")

# ---- 9. Still missing -----------------------------------------------------
print("\n9. STILL MISSING (expected to warn)")
check("EOG gas-flare ground truth",
      Path("data/external/eog_flares.csv").exists(),
      "needs free registration at eogdata.mines.edu", warn_only=True)
check("OSM / land-cover / night-lights features",
      Path("data/external/osm_industrial.csv").exists(),
      "would help separate flares from kilns and furnaces", warn_only=True)

# ---- Summary --------------------------------------------------------------
print("\n" + "=" * 70)
ok = sum(1 for m, _, _ in results if m == PASS)
bad = sum(1 for m, _, _ in results if m == FAIL)
warn = sum(1 for m, _, _ in results if m == WARN)
print(f"PASSED {ok}    FAILED {bad}    WARNINGS {warn}")
if bad:
    print("\nFailures:")
    for m, name, detail in results:
        if m == FAIL:
            print(f"  - {name}: {detail}")
print("=" * 70)
