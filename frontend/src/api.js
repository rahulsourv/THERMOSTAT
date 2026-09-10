// All talking to the backend happens here, so components stay simple.

// Empty: requests go to the SAME origin the page came from, and Vite's
// dev-server proxy forwards /api to FastAPI. See vite.config.js.
const BASE = "";

async function get(path) {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

export const api = {
  summary: () => get("/api/summary"),
  runs: (limit = 5) => get(`/api/runs?limit=${limit}`),
  place: (cellId) => get(`/api/places/${cellId}`),

  classification: () => get("/api/classification"),

  alerts: ({ level, eventClass, limit = 50, confirmedOnly = false } = {}) => {
    const params = new URLSearchParams({ limit });
    if (level) params.set("level", level);
    if (eventClass) params.set("event_class", eventClass);
    if (confirmedOnly) params.set("confirmed_only", "true");
    return get(`/api/alerts?${params}`);
  },

  fires: ({ minFrp = 0, limit = 60 } = {}) =>
    get(`/api/fires?min_frp=${minFrp}&limit=${limit}`),

  firesGeojson: ({ minFrp = 0, limit = 1500 } = {}) =>
    get(`/api/fires/geojson?min_frp=${minFrp}&limit=${limit}`),

  geojson: ({ level, eventClass, limit = 800 } = {}) => {
    const params = new URLSearchParams({ limit, one_per_place: "true" });
    if (level) params.set("level", level);
    if (eventClass) params.set("event_class", eventClass);
    return get(`/api/alerts/geojson?${params}`);
  },
};

// ---------------------------------------------------------------------------
// SIH26162 event taxonomy.
//
// The per-class tones below are for BADGES and LISTS, where the text label is
// always present and colour is a secondary cue. They are deliberately NOT used
// to colour the map: as an all-pairs palette these eleven hues fail
// colour-blindness separation (crop-burning green and wildfire green came out
// 5.7 apart against a floor of 15). The map colours by FAMILY_TONE instead.
// ---------------------------------------------------------------------------
// Plain-language names and one-line explanations. The dashboard is read by
// people who did not build the model, so "static thermal anomaly" is not a
// label - it is jargon that hides what the row actually means.
export const EVENT_CLASSES = [
  { id: "gas_flare", label: "Gas flare", icon: "local_fire_department",
    tone: "#dc2626", group: "Industrial",
    blurb: "Waste gas burnt off continuously at an oil or gas field." },
  { id: "oil_refinery", label: "Oil refinery", icon: "oil_barrel",
    tone: "#ea580c", group: "Industrial",
    blurb: "Refinery or petrochemical plant processing crude oil." },
  { id: "thermal_power_plant", label: "Power plant", icon: "bolt",
    tone: "#f59e0b", group: "Industrial",
    blurb: "Coal, gas or oil fired power station generating electricity." },
  { id: "industrial_heat", label: "Factory or kiln", icon: "factory",
    tone: "#b45309", group: "Industrial",
    blurb: "Steelworks, smelter, cement plant or brick kiln." },
  { id: "mining", label: "Mine or quarry", icon: "landslide",
    tone: "#78716c", group: "Industrial",
    blurb: "Open-cast mine or quarry with persistent heat." },
  { id: "industrial_unspecified", label: "Industrial (type unknown)", icon: "help_center",
    tone: "#94631b", group: "Industrial",
    blurb: "Certainly a steady industrial heat source, but the satellite behaviour alone cannot say which kind." },
  { id: "volcano", label: "Volcano", icon: "volcano",
    tone: "#7c3aed", group: "Natural",
    blurb: "Natural geothermal heat, matched to the Smithsonian volcano register." },
  { id: "wildfire", label: "Wildfire", icon: "forest",
    tone: "#16a34a", group: "Natural",
    blurb: "A forest or bush fire burning right now - hot, spreading, short lived." },
  { id: "agricultural_burning", label: "Crop burning", icon: "agriculture",
    tone: "#65a30d", group: "Natural",
    blurb: "Seasonal daytime field burning after harvest." },
  { id: "unknown", label: "Unresolved", icon: "help",
    tone: "#94a3b8", group: "Unresolved",
    blurb: "Seen before, but its behaviour does not match any category confidently." },
  { id: "unclassified", label: "Brand new location", icon: "fiber_new",
    tone: "#cbd5e1", group: "Unresolved",
    blurb: "First time anything has burnt here - there is no history to judge it against." },
];

/**
 * A Google Maps link for a coordinate.
 *
 * Uses the documented ?api=1 search URL rather than a raw /maps/@ path: it is
 * the supported form, works on desktop and deep-links into the mobile app,
 * and drops a labelled pin instead of only recentring the camera.
 */
export const gmapsUrl = (lat, lon) =>
  `https://www.google.com/maps/search/?api=1&query=${lat.toFixed(6)},${lon.toFixed(6)}`;

/** Same spot, but in Google's satellite view at building scale. */
export const gmapsSatelliteUrl = (lat, lon) =>
  `https://www.google.com/maps/@?api=1&map_action=map&center=${lat.toFixed(6)},${lon.toFixed(6)}&zoom=17&basemap=satellite`;

// Three families, not ten classes. Colour on a map is an all-pairs problem -
// any two classes can end up side by side - and a validated palette caps that
// at three hues. The specific type is carried by the label and popup instead.
export const FAMILY_TONE = {
  Industrial: "#eb6834",
  Natural: "#1baf7a",
  Unresolved: "#94a3b8",
};

export const CLASS_BY_ID = Object.fromEntries(
  EVENT_CLASSES.map((c) => [c.id, c])
);

export const classInfo = (id) =>
  CLASS_BY_ID[id] || CLASS_BY_ID.unclassified;

// How the type was decided. Shown everywhere a class is shown, because a
// mapped fact and a model guess must never look like the same claim.
export const CLASS_SOURCES = {
  mapped:    { label: "Mapped",    tone: "#16a34a", hint: "Matched OpenStreetMap, WRI or Smithsonian ground truth" },
  predicted: { label: "Predicted", tone: "#2563eb", hint: "Stage-2 classifier's answer for a place nobody has mapped" },
  rule:      { label: "Rule",      tone: "#64748b", hint: "Transient heuristic on FRP, day/night mix and seasonality" },
  none:        { label: "None",      tone: "#94a3b8", hint: "No 2025 history at this location, so it cannot be typed" },
  stage1_only: { label: "Unspecified", tone: "#94631b", hint: "Confirmed as a steady industrial source, but the model is not confident enough to name the industry" },
};

// Fire severity uses a heat ramp: the bigger the fire, the darker the red.
export const FIRE_COLOURS = {
  Large: "#b91c1c",
  Moderate: "#ea580c",
  Small: "#eab308",
};

export const LEVEL_COLOURS = {
  High: "#dc2626",
  Medium: "#f59e0b",
  Low: "#2563eb",
  "Natural (volcano)": "#7c3aed",
};
