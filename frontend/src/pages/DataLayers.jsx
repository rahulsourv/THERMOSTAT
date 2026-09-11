import { useEffect, useState } from "preact/hooks";
import { api } from "../api.js";
import { Icon, n } from "../components/ui.jsx";
import { PageHeader, Section, Kpi } from "../components/layout.jsx";

/**
 * Every dataset in the system and the ONE job it is allowed to do.
 *
 * The role column is the point of the page. A register used to evaluate the
 * model must never also be a model input, or the evaluation proves nothing;
 * this makes that separation visible rather than buried in code.
 */
const ROLE = {
  feature: ["Model input", "#1d4ed8"],
  label: ["Builds labels", "#b45309"],
  eval: ["Evaluation only", "#15803d"],
  context: ["Display context", "#52525b"],
};

export function DataLayers() {
  const [s, setS] = useState(null);
  const [m, setM] = useState(null);
  useEffect(() => { api.summary().then(setS); api.metrics().then(setM).catch(() => setM({})); }, []);

  const t = s?.totals;
  const layers = [
    { name: "NASA FIRMS · VIIRS NOAA-20 active fire", icon: "satellite_alt", role: "feature",
      meta: `NASA LANCE · 375 m · point vector · ${t ? n(t.total_alerts) : "…"} detections in the current window`,
      note: "The only source of model features: power, brightness temperature, timing, persistence, geometry." },
    { name: "ThermoStats persistent place register", icon: "grid_on", role: "feature",
      meta: `0.05° cells · ${t ? n(t.places_in_reference) : "…"} places scored on a full year of 2025 behaviour`,
      note: "Built from the FIRMS archive above. NASA's own fire_type field is never read." },
    { name: "Global industrial heat sources (IHS v3.0)", icon: "verified", role: "label",
      meta: "Ma et al. 2023 · 25,544 objects · field-verified against POI and imagery",
      note: "Supplies Stage-1 labels. Its membership is never a feature — present for 1.4% of cells, it would leak the answer." },
    { name: "OpenStreetMap industrial features", icon: "factory", role: "label",
      meta: `Overpass API · ${m?.dbscan?.osm_validation?.features_available ? n(m.dbscan.osm_validation.features_available) : "53,053"} features`,
      note: "Labels source types and validates DBSCAN clusters. Distance to OSM is never a feature — it is the label." },
    { name: "WRI Global Power Plant Database", icon: "bolt", role: "eval",
      meta: "11,199 thermal plants (coal, gas, oil, biomass, waste)",
      note: "Held out of features AND labels, so it stays the one honest independent check." },
    { name: "Smithsonian Global Volcanism Program", icon: "volcano", role: "context",
      meta: "Holocene volcano catalogue · 10 km match radius",
      note: "Separates natural geothermal heat from industry in the display." },
  ];

  return (
    <>
      <PageHeader eyebrow="Geospatial layers" title="Data layers & satellite feeds"
                  sub="What feeds the engine, and the single role each dataset is allowed" />
      <div class="grid gap-3 mt-6 grid-cols-2 xl:grid-cols-4">
        <Kpi label="Detections in window" icon="radar" value={t && n(t.total_alerts)} />
        <Kpi label="Places registered" icon="grid_on" value={t && n(t.places_in_reference)} />
        <Kpi label="New locations" icon="bolt" value={t && n(t.new_locations)} />
        <Kpi label="Datasets" icon="layers" value={layers.length} />
      </div>
      <Section idx="01" title="Layer registry" note="Role separation is enforced in the pipeline">
        <div class="flex flex-col gap-3">
          {layers.map((l) => {
            const [label, tone] = ROLE[l.role];
            return (
              <div key={l.name} class="panel p-4 flex items-start gap-4 flex-wrap">
                <Icon name={l.icon} style="font-size:26px" />
                <div class="flex-1 min-w-[260px]">
                  <p class="m-0 text-[15px] font-semibold">{l.name}</p>
                  <p class="mono m-0 mt-1 text-[12px] text-muted">{l.meta}</p>
                  <p class="m-0 mt-2 text-[13px] leading-[19px]">{l.note}</p>
                </div>
                <span class="pill h-7 px-2.5" style={`color:${tone};border-color:${tone}`}>
                  <span class="pill-dot" style={`background:${tone}`} />{label}
                </span>
              </div>
            );
          })}
        </div>
      </Section>
    </>
  );
}
