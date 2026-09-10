from pathlib import Path

import folium
import pandas as pd


INPUT_FILE = Path("data/processed/live_hybrid_alerts.csv")
OUTPUT_FILE = Path("outputs/maps/live_industrial_alerts.html")

df = pd.read_csv(INPUT_FILE)

# Show the 1,000 most important current alerts.
df = df.head(1000)

alert_map = folium.Map(
    location=[20, 0],
    zoom_start=2,
    tiles="OpenStreetMap",
)

for _, row in df.iterrows():
    if row["alert_level"] == "High":
        color = "red"
    elif row["alert_level"] == "Medium":
        color = "orange"
    else:
        color = "blue"

    popup_html = f"""
    <b>Hybrid Thermal Alert</b><br>
    Alert score: {row["hybrid_alert_score"]}/100<br>
    Alert level: {row["alert_level"]}<br><br>

    <b>Live detection</b><br>
    Date: {row["acq_date"]}<br>
    Time: {str(row["acq_time"]).zfill(4)} UTC<br>
    FRP: {row["frp"]:.2f}<br>
    FIRMS confidence: {row["confidence"]}<br><br>

    <b>ML + historical evidence</b><br>
    ML static-source probability:
    {row["static_source_probability"]:.1%}<br>
    Historical risk: {row["historical_risk"]}/100<br>
    Historical match: {row["historical_match"]}
    """

    folium.CircleMarker(
        location=[row["latitude"], row["longitude"]],
        radius=6,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.8,
        popup=folium.Popup(popup_html, max_width=280),
    ).add_to(alert_map)

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
alert_map.save(OUTPUT_FILE)

print(f"Hybrid alerts displayed: {len(df):,}")
print(f"Saved map to: {OUTPUT_FILE}")