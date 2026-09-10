from pathlib import Path

import folium
from folium.plugins import MarkerCluster
import pandas as pd


# Load the newest downloaded FIRMS dataset.
data_dir = Path("data/raw/firms")
latest_file = max(data_dir.glob("*.csv"), key=lambda file: file.stat().st_mtime)
df = pd.read_csv(latest_file)

# Start the map centred roughly on India.
world_bounds = [[-85, -180], [85, 180]]

fire_map = folium.Map(
    location=[20, 0],
    zoom_start=2,
    min_zoom=2,
    max_bounds=True,
    tiles=None,
)

folium.TileLayer(
    tiles="OpenStreetMap",
    attr="© OpenStreetMap contributors",
    no_wrap=True,
).add_to(fire_map)

fire_map.fit_bounds(world_bounds)

# Groups nearby detections while zoomed out.
marker_cluster = MarkerCluster().add_to(fire_map)

for _, row in df.iterrows():
    frp = row["frp"]

    if frp >= 15:
        color = "red"
    elif frp >= 5:
        color = "orange"
    else:
        color = "yellow"

    popup = f"""
    <b>Thermal detection</b><br>
    Date: {row["acq_date"]}<br>
    Time: {row["acq_time"]}<br>
    FRP: {frp}<br>
    Temperature: {row["bright_ti4"]} K<br>
    Confidence: {row["confidence"]}<br>
    Day/Night: {row["daynight"]}
    """

    folium.CircleMarker(
        location=[row["latitude"], row["longitude"]],
        radius=5,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.7,
        popup=folium.Popup(popup, max_width=250),
    ).add_to(marker_cluster)

# Save the interactive map as an HTML file.
output_dir = Path("outputs/maps")
output_dir.mkdir(parents=True, exist_ok=True)

output_file = output_dir / "firms_detections_map.html"
fire_map.save(output_file)

print(f"Map saved to: {output_file}")