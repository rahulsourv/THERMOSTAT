import { useEffect, useState } from "preact/hooks";
import { api, classInfo } from "../api.js";
import { Icon, n } from "../components/ui.jsx";
import { PageHeader, download } from "../components/layout.jsx";

const today = () => new Date().toISOString().slice(0, 10);

/** Export briefs built live from the API. Files are generated in the browser. */
export function Reports() {
  const [summary, setSummary] = useState(null);
  const [busy, setBusy] = useState(null);

  useEffect(() => { api.summary().then(setSummary); }, []);
  const t = summary?.totals;

  const reports = [
    {
      id: "digest", kind: "Real-time telemetry brief", title: "Executive thermal digest", icon: "summarize",
      body: t ? `${n(t.total_alerts)} detections, ${n(t.known_places)} at known sources, ${n(t.new_locations)} at new locations.` : "Loading…",
      build: async () => {
        const [s, c] = await Promise.all([api.summary(), api.classification()]);
        return [{ generated: new Date().toISOString(), ...s.totals,
                  ...Object.fromEntries(s.by_level.map((r) => [`level_${r.alert_level}`, r.count])),
                  ...Object.fromEntries(c.by_class.map((r) => [`class_${r.event_class}_${r.class_source}`, r.count])) }];
      },
    },
    {
      id: "alerts", kind: "Alert intelligence log", title: "Active alert stream", icon: "notifications",
      body: "The 2,000 highest-scoring current alerts with class, provenance and coordinates.",
      build: async () => (await api.alerts({ limit: 2000 })).alerts,
    },
    {
      id: "sources", kind: "Geospatial investigation file", title: "Persistent source register", icon: "location_on",
      body: "One row per high-alert place, with its type and a Google Maps link.",
      build: async () => (await api.geojson({ level: "High", limit: 5000 })).features.map((f) => ({
        cell_id: f.properties.cell_id, latitude: f.geometry.coordinates[1], longitude: f.geometry.coordinates[0],
        type: classInfo(f.properties.event_class).label, class_source: f.properties.class_source,
        persistence: f.properties.static_probability, score: f.properties.alert_score,
        google_maps: `https://www.google.com/maps/search/?api=1&query=${f.geometry.coordinates[1]},${f.geometry.coordinates[0]}`,
      })),
    },
    {
      id: "model", kind: "Model evaluation record", title: "Model report card", icon: "analytics",
      body: "Confusion matrices, per-class accuracy, DBSCAN validation and calibration, as measured.",
      json: true,
      build: async () => [await api.metrics()],
    },
  ];

  const run = async (r, kind) => {
    setBusy(`${r.id}-${kind}`);
    try {
      const rows = await r.build();
      // The model report is one nested object, exported as-is; everything
      // else is a list of flat rows.
      download(`thermostats_${r.id}_${today()}`, r.json ? rows[0] : rows, kind);
    } finally { setBusy(null); }
  };

  return (
    <>
      <PageHeader eyebrow="Intelligence output" title="Intelligence reports"
                  sub="Export live briefs straight from the satellite pipeline" />
      <div class="grid gap-4 mt-6" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr))">
        {reports.map((r) => (
          <div key={r.id} class="panel p-5 flex flex-col gap-3">
            <span class="label-caps flex items-center gap-2"><Icon name={r.icon} style="font-size:16px" />{r.kind} · {today()}</span>
            <h2 class="m-0 text-[20px] font-semibold">{r.title}</h2>
            <p class="m-0 text-[13px] text-muted leading-[19px] flex-1">{r.body}</p>
            <div class="flex gap-2">
              {!r.json && <button class="btn btn-primary flex-1" disabled={!!busy} onClick={() => run(r, "csv")}>
                {busy === `${r.id}-csv` ? "Preparing…" : "Export CSV"}</button>}
              <button class="btn flex-1" disabled={!!busy} onClick={() => run(r, "json")}>
                {busy === `${r.id}-json` ? "Preparing…" : "Export JSON"}</button>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
