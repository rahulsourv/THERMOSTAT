from pathlib import Path

import folium
import pandas as pd


INPUT_FILE = Path("data/processed/hotspot_labeling_sample.csv")
OUTPUT_FILE = Path("outputs/maps/hotspot_labeling_map.html")

df = pd.read_csv(INPUT_FILE)

review_map = folium.Map(
    location=[20, 0],
    zoom_start=2,
    tiles=None,
)

folium.TileLayer(
    "OpenStreetMap",
    name="Street map",
).add_to(review_map)

folium.TileLayer(
    tiles=(
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}"
    ),
    attr="Tiles © Esri",
    name="Satellite view",
).add_to(review_map)

for _, row in df.iterrows():
    latitude = row["latitude"]
    longitude = row["longitude"]

    osm_url = (
        f"https://www.openstreetmap.org/"
        f"?mlat={latitude}&mlon={longitude}#map=16/{latitude}/{longitude}"
    )

    google_maps_url = (
        "https://www.google.com/maps/search/"
        f"?api=1&query={latitude},{longitude}"
    )

    popup_html = f"""
    <b>{row["hotspot_id"]}</b><br>
    Active days: {row["active_days"]}<br>
    Total detections: {row["total_detections"]}<br>
    Average FRP: {row["average_frp"]:.2f}<br>
    Nighttime ratio: {row["nighttime_ratio"]:.2%}<br><br>
    <a href="{osm_url}" target="_blank">Open in OpenStreetMap</a><br>
    <a href="{google_maps_url}" target="_blank">Open in Google Maps</a>
    """

    folium.CircleMarker(
        location=[latitude, longitude],
        radius=6,
        color="red",
        fill=True,
        fill_color="red",
        fill_opacity=0.75,
        popup=folium.Popup(popup_html, max_width=280),
    ).add_to(review_map)

folium.LayerControl().add_to(review_map)

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
review_map.save(OUTPUT_FILE)

print(f"Saved review map to: {OUTPUT_FILE}")