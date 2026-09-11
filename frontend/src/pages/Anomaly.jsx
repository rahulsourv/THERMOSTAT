import { useEffect, useState } from "preact/hooks";
import { api, classInfo, LEVEL_COLOURS } from "../api.js";
import { MapLink, Loading, Empty, Icon, n, pct } from "../components/ui.jsx";
import { PageHeader, Kpi, Tabs, go } from "../components/layout.jsx";

const RISK = { High: "High risk", Medium: "Moderate risk", Low: "Low risk", "Natural (volcano)": "Natural" };

/** Places ranked by how steadily they burn, one card per place. */
export function Anomaly() {
  const [summary, setSummary] = useState(null);
  const [level, setLevel] = useState("High");
  const [geo, setGeo] = useState(null);
  const [limit, setLimit] = useState(48);

  useEffect(() => { api.summary().then(setSummary); }, []);
  useEffect(() => {
    setGeo(null);
    api.geojson({ level: level || undefined, limit }).then(setGeo);
  }, [level, limit]);

  const lv = (k) => summary?.by_level.find((r) => r.alert_level === k)?.count;
  const total = summary?.totals.total_alerts;
  const cards = (geo?.features || []).map((f) => ({ ...f.properties, lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] }))
    .sort((a, b) => b.alert_score - a.alert_score);

  return (
    <>
      <PageHeader eyebrow="Change & anomaly analysis" title="Thermal anomaly intelligence"
                  sub="Places ranked by persistence of heat, strongest first" />
      <div class="grid gap-3 mt-6 grid-cols-2 xl:grid-cols-4">
        <Kpi label="High risk" icon="warning" tone="var(--color-high)" value={n(lv("High"))} />
        <Kpi label="Moderate risk" icon="error" tone="var(--color-medium)" value={n(lv("Medium"))} />
        <Kpi label="Natural (volcano)" icon="volcano" tone="var(--color-volcano)" value={n(lv("Natural (volcano)"))} />
        <Kpi label="Total alerts logged" icon="list_alt" value={n(total)} />
      </div>

      <div class="panel mt-6">
        <div class="px-4 py-3 border-b border-rule flex items-center justify-between gap-3 flex-wrap">
          <p class="m-0 text-[14px] font-semibold">Detected anomaly sources ({n(cards.length)})</p>
          <Tabs value={level} onChange={(v) => { setLevel(v); setLimit(48); }}
                options={[{ label: "All", value: "" }, { label: "High", value: "High" }, { label: "Medium", value: "Medium" },
                          { label: "Low", value: "Low" }, { label: "Volcano", value: "Natural (volcano)" }]} />
        </div>
        <div class="p-4">
          {!geo ? <Loading /> : cards.length === 0 ? <Empty title="No sources at this level" /> : (
            <div class="grid gap-3" style="grid-template-columns:repeat(auto-fill,minmax(270px,1fr))">
              {cards.map((c) => {
                const info = classInfo(c.event_class);
                return (
                  <div key={c.cell_id} class="panel-flat p-3.5 flex flex-col gap-2">
                    <div class="flex items-center justify-between gap-2">
                      <span class="mono text-[13px] font-bold">CELL_{c.cell_id}</span>
                      <span class="pill border-current" style={`color:${LEVEL_COLOURS[c.alert_level] || "inherit"}`}>{RISK[c.alert_level] || c.alert_level}</span>
                    </div>
                    <span class="flex items-center gap-1.5 text-[12px] font-semibold">
                      <Icon name={info.icon} style={`font-size:16px;color:${info.tone}`} />{info.label}
                    </span>
                    <span class="mono text-[12px]">{c.lat.toFixed(4)}° N, {c.lon.toFixed(4)}° E</span>
                    <span class="text-[11px] font-bold uppercase text-muted">
                      Persistence {pct(c.static_probability)} · score {c.alert_score}
                    </span>
                    <div class="flex gap-2 mt-1">
                      <button class="btn btn-primary h-8 flex-1" onClick={() => go(`investigation/${c.cell_id}`)}>Inspect telemetry</button>
                      <MapLink lat={c.lat} lon={c.lon} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          {geo && cards.length >= limit && (
            <div class="flex justify-center mt-4"><button class="btn" onClick={() => setLimit(limit + 48)}>Load more</button></div>
          )}
        </div>
      </div>
    </>
  );
}
