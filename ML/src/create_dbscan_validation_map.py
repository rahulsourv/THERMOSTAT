"""
Interactive map for eyeballing whether DBSCAN clusters sit on real industry.

Run dbscan_cluster_analysis.py first - this reads its output.

The map is built for VALIDATION, not decoration, so it is arranged around
the question "is there actually a factory here?":

  * every clustered cell is drawn and coloured by its cluster, so a cluster
    reads as one object rather than a scatter of dots
  * the OpenStreetMap features we matched against are a separate toggleable
    layer, drawn as hollow squares so they never hide a thermal point
  * noise points are on their own layer, off by default - they are 80% of
    the data and would otherwise bury everything
  * a side panel lists clusters worst-first, because the interesting
    validation work is on the ones that did NOT match
  * clicking a panel entry flies to that cluster at zoom 13, which is close
    enough to see the plant in the basemap
"""

from __future__ import annotations

import json
from pathlib import Path

import folium
import numpy as np
import pandas as pd
from folium.plugins import Fullscreen, MeasureControl, MiniMap
from scipy.spatial import cKDTree

CLUSTERS_FILE = Path("data/processed/dbscan_clusters.csv")
SUMMARY_FILE = Path("data/processed/dbscan_cluster_summary.csv")
METRICS_FILE = Path("models/dbscan_metrics.json")
OSM_FILE = Path("data/external/osm_features.csv")
OUTPUT_FILE = Path("outputs/maps/dbscan_osm_validation.html")

EARTH_RADIUS_KM = 6371.0
# Only OSM features near a cluster are drawn. All 36,000 would make a file
# too big to open and would say nothing about the clusters anyway.
OSM_DRAW_RADIUS_KM = 12.0

VERDICT_COLOUR = {
    "confirmed": "#16a34a",
    "contradicted": "#dc2626",
    "unchecked": "#94a3b8",
}
VERDICT_LABEL = {
    "confirmed": "Industry mapped within 3 km",
    "contradicted": "Queried, nothing mapped nearby",
    "unchecked": "OSM fetch has not covered this area yet",
}

OSM_COLOUR = {
    "gas_flare": "#dc2626",
    "oil_refinery": "#ea580c",
    "power_plant": "#f59e0b",
    "industrial_works": "#b45309",
    "mining": "#78716c",
    "kiln": "#a16207",
    "smelter": "#9a3412",
}

# 20 hues that stay distinguishable next to each other. Cluster ids cycle
# through them; adjacent clusters are rarely adjacent in id, so repeats
# almost never touch on screen.
PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#393b79", "#637939", "#8c6d31", "#843c39", "#7b4173",
    "#3182bd", "#e6550d", "#31a354", "#756bb1", "#636363",
]


def to_xyz(lat, lon):
    lat_r, lon_r = np.radians(lat), np.radians(lon)
    return np.column_stack([
        np.cos(lat_r) * np.cos(lon_r),
        np.cos(lat_r) * np.sin(lon_r),
        np.sin(lat_r),
    ])


def nearby_osm(osm, clustered):
    """Keep only OSM features within OSM_DRAW_RADIUS_KM of a clustered cell."""
    tree = cKDTree(to_xyz(clustered.latitude.values, clustered.longitude.values))
    chord, _ = tree.query(to_xyz(osm.latitude.values, osm.longitude.values))
    km = 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2, 0, 1))
    return osm[km <= OSM_DRAW_RADIUS_KM].copy()


def build():
    places = pd.read_csv(CLUSTERS_FILE)
    summary = pd.read_csv(SUMMARY_FILE)
    metrics = json.loads(METRICS_FILE.read_text(encoding="utf-8"))
    osm = pd.read_csv(OSM_FILE)

    clustered = places[places.cluster != -1]
    noise = places[places.cluster == -1]
    osm_near = nearby_osm(osm, clustered)

    print(f"Clustered cells : {len(clustered):,}")
    print(f"Noise cells     : {len(noise):,}")
    print(f"OSM drawn       : {len(osm_near):,} of {len(osm):,} "
          f"(within {OSM_DRAW_RADIUS_KM} km of a cluster)")

    verdict_of = dict(zip(summary.cluster, summary.verdict))

    fmap = folium.Map(location=[25, 45], zoom_start=3, tiles=None,
                      world_copy_jump=False)
    # Order matters: Leaflet activates the LAST base layer added, and the
    # OSM basemap is the one being validated against, so it goes last.
    folium.TileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}",
        name="Satellite imagery", attr="Esri, Maxar, Earthstar Geographics",
        no_wrap=True, max_zoom=19,
    ).add_to(fmap)
    folium.TileLayer(
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        name="OpenStreetMap", attr="© OpenStreetMap contributors",
        no_wrap=True, max_zoom=19,
    ).add_to(fmap)

    # ---- Layer: OSM industrial features ---------------------------------
    osm_layer = folium.FeatureGroup(name=f"OSM industry ({len(osm_near):,})",
                                    show=True)
    for _, r in osm_near.iterrows():
        colour = OSM_COLOUR.get(r.osm_class, "#334155")
        folium.RegularPolygonMarker(
            location=[r.latitude, r.longitude],
            number_of_sides=4, radius=5, rotation=45,
            color=colour, weight=2, fill=False,
            tooltip=(
                f"{r.osm_class.replace('_', ' ')}: "
                f"{r['name'] if isinstance(r['name'], str) and r['name'] else '(unnamed)'}"
            ),
        ).add_to(osm_layer)
    osm_layer.add_to(fmap)

    # ---- Layer: clustered thermal cells ---------------------------------
    cluster_layer = folium.FeatureGroup(
        name=f"DBSCAN clusters ({len(clustered):,} cells)", show=True)
    for _, r in clustered.iterrows():
        cid = int(r.cluster)
        verdict = verdict_of.get(cid, "unchecked")
        folium.CircleMarker(
            location=[r.latitude, r.longitude],
            radius=5,
            color=VERDICT_COLOUR[verdict],   # outline = does it check out
            weight=2,
            fill=True,
            fill_color=PALETTE[cid % len(PALETTE)],   # fill = which cluster
            fill_opacity=0.85,
            popup=folium.Popup(
                f"<b>Cluster {cid}</b> &middot; "
                f"<span style='color:{VERDICT_COLOUR[verdict]}'>{verdict}</span><br>"
                f"{r.latitude:.4f}, {r.longitude:.4f}<br><br>"
                f"static probability: <b>{r.static_probability:.3f}</b><br>"
                f"active {int(r.active_days)} days, "
                f"{int(r.months_active)} months<br>"
                f"night fraction: {r.night_fraction:.0%}<br><br>"
                f"nearest OSM: <b>{r.nearest_osm_class}</b> "
                f"{r.km_to_osm:.2f} km<br>"
                f"{r.nearest_osm_name if isinstance(r.nearest_osm_name, str) else ''}",
                max_width=300,
            ),
            tooltip=f"Cluster {cid} ({verdict})",
        ).add_to(cluster_layer)
    cluster_layer.add_to(fmap)

    # ---- Layer: cluster centroids ---------------------------------------
    centroid_layer = folium.FeatureGroup(
        name=f"Cluster labels ({len(summary):,})", show=True)
    for _, c in summary.iterrows():
        colour = VERDICT_COLOUR[c.verdict]
        folium.Marker(
            location=[c.latitude, c.longitude],
            icon=folium.DivIcon(html=(
                f'<div style="font:600 10px/1 system-ui;color:#fff;'
                f'background:{colour};border-radius:9px;padding:2px 5px;'
                f'white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,.4)">'
                f'{int(c.cluster)}</div>'
            )),
            popup=folium.Popup(
                f"<b>Cluster {int(c.cluster)}</b><br>"
                f"<span style='color:{colour}'><b>{c.verdict.upper()}</b></span> "
                f"&mdash; {VERDICT_LABEL[c.verdict]}<br><br>"
                f"<b>{int(c.points)}</b> thermal cells over "
                f"<b>{c.extent_km:.1f} km</b><br>"
                f"{int(c.members_matched)} of {int(c.points)} cells matched "
                f"({c.match_rate:.0%})<br><br>"
                f"nearest industry: <b>{c.dominant_osm_class or '—'}</b> at "
                f"{c.nearest_osm_km:.2f} km<br>"
                f"{c.nearest_osm_name if isinstance(c.nearest_osm_name, str) else ''}"
                f"<br><br>mean static probability "
                f"{c.mean_static_probability:.3f}<br>"
                f"mean night fraction {c.mean_night_fraction:.0%}<br>"
                f"mean active days {c.mean_active_days:.0f}"
                + ("<br><br><b style='color:#7c3aed'>VOLCANIC</b>"
                   if c.is_volcanic else "")
                + ("<br><b style='color:#16a34a'>WRI power plant nearby</b>"
                   if c.near_power_plant else ""),
                max_width=320,
            ),
        ).add_to(centroid_layer)
    centroid_layer.add_to(fmap)

    # ---- Layer: noise, off by default -----------------------------------
    noise_layer = folium.FeatureGroup(
        name=f"Noise / unclustered ({len(noise):,})", show=False)
    for _, r in noise.iterrows():
        folium.CircleMarker(
            location=[r.latitude, r.longitude],
            radius=2, color="#94a3b8", weight=1,
            fill=True, fill_color="#cbd5e1", fill_opacity=0.5,
            tooltip=(f"Noise · p={r.static_probability:.2f} · "
                     f"OSM {r.km_to_osm:.1f} km"),
        ).add_to(noise_layer)
    noise_layer.add_to(fmap)

    Fullscreen().add_to(fmap)
    MiniMap(toggle_display=True, minimized=True).add_to(fmap)
    MeasureControl(primary_length_unit="kilometers").add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)

    add_panels(fmap, summary, metrics)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(OUTPUT_FILE))
    size_mb = OUTPUT_FILE.stat().st_size / 1e6
    print(f"\nSaved map to: {OUTPUT_FILE}  ({size_mb:.1f} MB)")
    return OUTPUT_FILE


def add_panels(fmap, summary, metrics):
    """Legend, headline metrics, and a jump-to-cluster list."""
    osm_meta = metrics["osm_validation"]
    confirmed = osm_meta["clusters_confirmed"]
    contradicted = osm_meta["clusters_contradicted"]
    unchecked = osm_meta["clusters_unchecked"]

    # Worst first: the point of the panel is to find the failures.
    order = {"contradicted": 0, "unchecked": 1, "confirmed": 2}
    listed = summary.sort_values(
        by=["verdict", "points"],
        key=lambda s: s.map(order) if s.name == "verdict" else -s,
    ).head(120)

    rows = "".join(
        f'<li data-lat="{r.latitude}" data-lon="{r.longitude}">'
        f'<span class="dot" style="background:{VERDICT_COLOUR[r.verdict]}"></span>'
        f'<b>#{int(r.cluster)}</b> {int(r.points)} cells'
        f'<span class="km">{r.nearest_osm_km:.1f} km</span></li>'
        for _, r in listed.iterrows()
    )

    legend = "".join(
        f'<div class="row"><span class="sq" style="border-color:{colour}"></span>'
        f'{name.replace("_", " ")}</div>'
        for name, colour in OSM_COLOUR.items()
    )

    html = f"""
<div id="ts-panel">
  <div class="hd">DBSCAN &times; OpenStreetMap validation</div>
  <div class="mt">
    <b>{metrics['clusters']}</b> clusters from
    <b>{metrics['points']:,}</b> persistent thermal cells<br>
    eps <b>{metrics['parameters']['eps_km']} km</b>,
    min_samples <b>{metrics['parameters']['min_samples']}</b>,
    noise <b>{metrics['noise_pct']}%</b>,
    silhouette <b>{metrics['silhouette']}</b>
  </div>
  <div class="verdicts">
    <span style="color:{VERDICT_COLOUR['confirmed']}">&#9679; {confirmed} confirmed</span>
    <span style="color:{VERDICT_COLOUR['contradicted']}">&#9679; {contradicted} contradicted</span>
    <span style="color:{VERDICT_COLOUR['unchecked']}">&#9679; {unchecked} unchecked</span>
  </div>
  <div class="note">
    Marker <b>outline</b> = verdict. Marker <b>fill</b> = which cluster.
    Hollow squares are mapped OSM industry.
    &ldquo;Unchecked&rdquo; means the Overpass fetch has not reached that
    region yet &mdash; it is not evidence of absence.
  </div>
  <div class="hd2">OSM feature types</div>
  {legend}
  <div class="hd2">Jump to a cluster &mdash; failures first</div>
  <ul id="ts-list">{rows}</ul>
</div>
<style>
  #ts-panel {{
    position: fixed; top: 12px; left: 12px; z-index: 9999;
    width: 268px; max-height: calc(100vh - 24px); overflow-y: auto;
    background: #fff; border: 1px solid #cbd5e1; border-radius: 10px;
    padding: 12px; font: 12px/1.45 system-ui, sans-serif; color: #0f172a;
    box-shadow: 0 4px 14px rgba(15,23,42,.18);
  }}
  #ts-panel .hd {{ font-weight: 700; font-size: 13px; margin-bottom: 6px; }}
  #ts-panel .hd2 {{
    font-weight: 700; font-size: 10px; letter-spacing: .06em;
    text-transform: uppercase; color: #64748b;
    margin: 10px 0 5px; border-top: 1px solid #e2e8f0; padding-top: 8px;
  }}
  #ts-panel .mt {{ color: #475569; }}
  #ts-panel .verdicts {{
    display: flex; flex-direction: column; gap: 2px;
    margin-top: 7px; font-weight: 600;
  }}
  #ts-panel .note {{
    margin-top: 7px; color: #64748b; font-size: 11px;
    background: #f8fafc; border-radius: 6px; padding: 6px 7px;
  }}
  #ts-panel .row {{ display: flex; align-items: center; gap: 6px; }}
  #ts-panel .sq {{
    width: 9px; height: 9px; border: 2px solid; transform: rotate(45deg);
    display: inline-block; flex: none;
  }}
  #ts-list {{ list-style: none; margin: 0; padding: 0; }}
  #ts-list li {{
    display: flex; align-items: center; gap: 6px;
    padding: 3px 4px; border-radius: 5px; cursor: pointer;
  }}
  #ts-list li:hover {{ background: #f1f5f9; }}
  #ts-list .dot {{
    width: 8px; height: 8px; border-radius: 50%; flex: none;
  }}
  #ts-list .km {{ margin-left: auto; color: #64748b; font-size: 11px; }}
</style>
<script>
  document.addEventListener('DOMContentLoaded', function () {{
    var map = {fmap.get_name()};
    document.querySelectorAll('#ts-list li').forEach(function (li) {{
      li.addEventListener('click', function () {{
        // Zoom 13 is close enough that a refinery or quarry is obvious in
        // the basemap, which is the whole point of this list.
        map.setView([+li.dataset.lat, +li.dataset.lon], 13);
      }});
    }});
  }});
</script>
"""
    fmap.get_root().html.add_child(folium.Element(html))


if __name__ == "__main__":
    build()
