"""
Map of the place-level alerts.

One marker = one PLACE, not one detection. The old map drew every
detection, so a single flare seen 40 times looked like 40 alerts.
"""

from pathlib import Path

import folium
import pandas as pd

INPUT_FILE = Path("data/processed/live_hotspot_alerts.csv")
OUTPUT_FILE = Path("outputs/maps/hotspot_alerts_map.html")

TOP_PLACES = 600

df = pd.read_csv(INPUT_FILE)

# Collapse repeated detections down to one row per place.
places = (
    df.sort_values("alert_score", ascending=False)
    .drop_duplicates(subset="cell_id")
    .head(TOP_PLACES)
)

# no_wrap stops the world repeating endlessly left to right.
alert_map = folium.Map(
    location=[20, 0], zoom_start=2, min_zoom=2,
    max_bounds=True, tiles=None,
)
folium.TileLayer(
    tiles="OpenStreetMap",
    attr="(c) OpenStreetMap contributors",
    no_wrap=True,
).add_to(alert_map)

colours = {
    "High": "red",
    "Medium": "orange",
    "Low": "blue",
    "Natural (volcano)": "purple",
}

for _, row in places.iterrows():
    colour = colours.get(row["alert_level"], "blue")

    if row["near_power_plant"]:
        verdict = (
            "<span style='color:green'><b>CONFIRMED</b> - known thermal "
            f"power plant {row['km_to_thermal_plant']:.1f} km away</span>"
        )
    elif row["is_volcanic"]:
        verdict = (
            "<span style='color:purple'><b>NATURAL</b> - volcano "
            f"{row['km_to_volcano']:.1f} km away, not industrial</span>"
        )
    else:
        verdict = (
            "<i>Unconfirmed persistent source. No power plant or volcano "
            "nearby in our reference data - could be a gas flare, kiln, "
            "furnace or a source we have no record of.</i>"
        )

    popup_html = f"""
    <b>Persistent thermal source</b><br>
    Alert score: {row["alert_score"]}/100 ({row["alert_level"]})<br>
    Model probability: {row["static_probability"]:.1%}<br><br>

    <b>Why</b><br>
    {row["why"]}<br><br>

    <b>Tonight</b><br>
    Date: {row["acq_date"]}<br>
    FRP: {row["frp"]:.1f}<br>
    Confidence: {row["confidence"]}<br><br>

    {verdict}
    """

    folium.CircleMarker(
        location=[row["latitude"], row["longitude"]],
        radius=6,
        color=colour,
        fill=True,
        fill_color=colour,
        fill_opacity=0.8,
        popup=folium.Popup(popup_html, max_width=300),
    ).add_to(alert_map)

n_confirmed = int(places["near_power_plant"].sum())
n_volcano = int(places["is_volcanic"].sum())

legend = f"""
<div style="position:fixed; bottom:30px; left:30px; z-index:9999;
     background:white; padding:10px 14px; border:1px solid #999;
     border-radius:4px; font:13px sans-serif; max-width:290px;">
  <b>Persistent thermal sources</b><br>
  <span style="color:red;">&#9679;</span> High &nbsp;
  <span style="color:orange;">&#9679;</span> Medium &nbsp;
  <span style="color:purple;">&#9679;</span> Volcano (natural)<br>
  <span style="font-size:11px;color:#666;">
  One marker = one place, scored on a year of 2025 behaviour.<br>
  {n_confirmed} of {len(places)} shown are confirmed within 2 km of a
  known thermal power plant. {n_volcano} are volcanoes.<br>
  Model never saw coordinates; tested on held-out regions.</span>
</div>
"""
alert_map.get_root().html.add_child(folium.Element(legend))

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
alert_map.save(OUTPUT_FILE)

print(f"Places shown: {len(places):,}")
print(places["alert_level"].value_counts().to_string())
print(f"Saved map to: {OUTPUT_FILE}")
