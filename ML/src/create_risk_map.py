from pathlib import Path

import folium
from folium.plugins import MarkerCluster
import pandas as pd


INPUT_FILE = Path("data/processed/risk_scored_hotspots_2025.csv")
OUTPUT_FILE = Path("outputs/maps/industrial_thermal_risk_map.html")

df = pd.read_csv(INPUT_FILE)

# Display only the highest-priority hotspots.
# Showing every worldwide point would make the browser slow.
df = df.head(1500)

risk_map = folium.Map(
    location=[20, 0],
    zoom_start=2,
    tiles="OpenStreetMap",
)

markers = MarkerCluster().add_to(risk_map)

for _, row in df.iterrows():
    if row["risk_level"] == "High":
        color = "red"
    elif row["risk_level"] == "Medium":
        color = "orange"
    else:
        color = "blue"

    popup_html = f"""
    <b>Industrial Thermal Risk</b><br>
    Risk score: {row["industrial_thermal_risk_score"]}/100<br>
    Risk level: {row["risk_level"]}<br>
    Active days: {row["active_days"]}<br>
    Total detections: {row["total_detections"]}<br>
    Average FRP: {row["average_frp"]:.2f}<br>
    Nighttime activity: {row["nighttime_ratio"]:.1%}<br>
    Coordinates: {row["latitude"]:.4f}, {row["longitude"]:.4f}
    """

    folium.CircleMarker(
        location=[row["latitude"], row["longitude"]],
        radius=6,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.75,
        popup=folium.Popup(popup_html, max_width=260),
    ).add_to(markers)

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
risk_map.save(OUTPUT_FILE)

print(f"Hotspots displayed: {len(df):,}")
print(f"Saved map to: {OUTPUT_FILE}")