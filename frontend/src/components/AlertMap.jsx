import { useEffect, useRef, useState } from "preact/hooks";
import L from "leaflet";
import { SEMANTIC } from "./ui.jsx";
import { classInfo, FAMILY_TONE, gmapsUrl } from "../api.js";

// Key-free basemaps only: CARTO's raster endpoint started demanding an API key
// and answering 400, which is why it is not offered here.
const TILES = {
  osm: { url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png", attr: "&copy; OpenStreetMap contributors" },
  satellite: { url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr: "Esri, Maxar, Earthstar Geographics" },
  topo: { url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}", attr: "Esri, HERE, Garmin, OpenStreetMap" },
};

/**
 * Leaflet map. Draws either industrial places or fire events.
 *
 * Leaflet manages its own DOM, so the map instance lives in a ref and is
 * updated by hand. Letting Preact re-render it would make it flicker and
 * throw away wherever the analyst had panned to.
 */
/** GeoJSON stores coordinates longitude-first; return them as [lat, lon]. */
const latlngOf = (feature) => [
  feature.geometry.coordinates[1],
  feature.geometry.coordinates[0],
];

export function AlertMap({
  geojson,
  onSelect,
  selectedCellId,
  mode = "industrial",
  colourBy = "level",
  basemap = "osm",
  height = 520,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const layerRef = useRef(null);
  const tileRef = useRef(null);
  const [view, setView] = useState({ lat: 20, lon: 10, zoom: 2 });

  useEffect(() => {
    if (mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: [20, 10],
      zoom: 2,
      minZoom: 2,
      zoomControl: false,
      worldCopyJump: false,
      maxBounds: [[-85, -180], [85, 180]],
      maxBoundsViscosity: 1,
    });

    // noWrap stops the world repeating endlessly left to right.
    // CARTO's voyager endpoint now requires an API key and answers 400 for
    // anonymous requests, so this uses OSM's own key-free tile server.
    tileRef.current = L.tileLayer(
      "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        attribution: "&copy; OpenStreetMap contributors",
        noWrap: true,
        maxZoom: 19,
      }
    ).addTo(map);

    L.control.zoom({ position: "topright" }).addTo(map);

    const sync = () => {
      const c = map.getCenter();
      setView({ lat: c.lat, lon: c.lng, zoom: map.getZoom() });
    };
    map.on("moveend zoomend", sync);

    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !geojson) return;

    if (layerRef.current) layerRef.current.remove();
    const isFire = mode === "fires";

    layerRef.current = L.geoJSON(geojson, {
      pointToLayer: (feature, latlng) => {
        const p = feature.properties;

        if (isFire) {
          // Radius scales with total FRP. Square root keeps one enormous
          // fire from drawing a circle that swallows a continent.
          const radius = Math.min(
            20, 3 + Math.sqrt(Number(p.total_frp) || 0) * 0.5
          );
          const colour = SEMANTIC[p.severity] || SEMANTIC.Small;
          return L.circleMarker(latlng, {
            radius, color: colour, weight: 1,
            fillColor: colour, fillOpacity: 0.45,
          });
        }

        const selected = p.cell_id === selectedCellId;
        // Colour by severity, or by what the source actually IS. The class
        // view is the SIH26162 answer: cause, not just intensity.
        // Family, not class: eleven hues on one map is an all-pairs palette
        // and fails CVD separation. Three families always pass, and the
        // popup names the exact type.
        const colour =
          colourBy === "class"
            ? FAMILY_TONE[classInfo(p.event_class).group] || FAMILY_TONE.Unresolved
            : SEMANTIC[p.alert_level] || SEMANTIC.muted;
        return L.circleMarker(latlng, {
          radius: selected ? 8 : 4.5,
          color: selected ? "#0f172a" : colour,
          weight: selected ? 2.5 : 1,
          fillColor: colour,
          fillOpacity: 0.8,
        });
      },

      onEachFeature: (feature, layer) => {
        const p = feature.properties;

        if (isFire) {
          layer.bindPopup(`
            <b>${p.severity} fire</b><br>
            Total intensity: <b>${p.total_frp} FRP</b><br>
            Peak pixel: ${p.max_frp} FRP<br>
            Detections: ${p.detections}<br>
            Latest: ${p.latest_date}<br><br>
            ${p.why}<br><br>
            <i>Actively burning now — a detection, not a forecast.</i>
          `);
          return;
        }

        const verdict = p.near_power_plant
          ? '<span style="color:#16a34a"><b>CONFIRMED</b> — known power plant nearby</span>'
          : p.is_volcanic
          ? '<span style="color:#7c3aed"><b>NATURAL</b> — volcano nearby</span>'
          : '<span style="color:#64748b"><b>UNCONFIRMED</b> — no reference match</span>';

        const klass = classInfo(p.event_class);
        const confidence =
          p.class_confidence != null
            ? ` · ${(p.class_confidence * 100).toFixed(0)}% confident`
            : "";
        const typeLine = p.event_class
          ? `<span style="color:${klass.tone}"><b>${klass.label.toUpperCase()}</b></span>
             <span style="color:#64748b">(${p.class_source || "none"}${confidence})</span><br>`
          : "";

        layer.bindPopup(`
          ${typeLine}
          <b>${p.alert_level}</b> · score ${p.alert_score}/100<br>
          Model probability: ${(p.static_probability * 100).toFixed(1)}%<br>
          FRP: ${p.frp}<br><br>${p.why}<br><br>${verdict}
          <br><br>
          <a href="${gmapsUrl(latlngOf(feature)[0], latlngOf(feature)[1])}"
             target="_blank" rel="noopener noreferrer"
             style="display:inline-flex;align-items:center;gap:5px;
                    font-weight:600;color:#2563eb;text-decoration:none">
            Open in Google Maps &rarr;
          </a>
        `);
        layer.on("click", () => onSelect && onSelect(p.cell_id));
      },
    }).addTo(map);
  }, [geojson, selectedCellId, mode, colourBy]);

  // Swap the basemap in place so the view (pan, zoom) survives the change.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const t = TILES[basemap] || TILES.osm;
    if (tileRef.current) tileRef.current.remove();
    tileRef.current = L.tileLayer(t.url, { attribution: t.attr, noWrap: true, maxZoom: 19 }).addTo(map);
    tileRef.current.bringToBack();
  }, [basemap]);

  const count = geojson?.features?.length ?? 0;

  return (
    <div class="relative">
      <div ref={containerRef} style={`height:${height}px;width:100%`} />

      {/* Telemetry strip: where the viewport is, and what feed is drawn. */}
      <div class="absolute bottom-3 left-3 right-3 z-[400] pointer-events-none flex justify-between gap-2 flex-wrap">
        <div class="pointer-events-auto bg-panel/95 backdrop-blur border border-rule rounded-[6px] px-2.5 py-1.5 flex items-center gap-2.5 text-[11px] text-muted shadow-sm">
          <span class="font-semibold text-ink">
            {Math.abs(view.lat).toFixed(1)}° {view.lat >= 0 ? "N" : "S"},{" "}
            {Math.abs(view.lon).toFixed(1)}° {view.lon >= 0 ? "E" : "W"}
          </span>
          <span class="text-edge">|</span>
          <span>Zoom {view.zoom}</span>
          <span class="text-edge">|</span>
          <span>VIIRS NOAA-20 375 m</span>
        </div>
        <div class="pointer-events-auto bg-panel/95 backdrop-blur border border-rule rounded-[6px] px-2.5 py-1.5 text-[11px] text-muted shadow-sm">
          <b class="text-ink">{count.toLocaleString()}</b>{" "}
          {mode === "fires" ? "fire events" : "places"} drawn
        </div>
      </div>
    </div>
  );
}
