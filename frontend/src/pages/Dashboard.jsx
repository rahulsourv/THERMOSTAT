import { useEffect, useState } from "preact/hooks";
import { api, EVENT_CLASSES, classInfo, FAMILY_TONE, LEVEL_COLOURS } from "../api.js";
import { AlertMap } from "../components/AlertMap.jsx";
import { ClassBadge, MapLink, Loading, Empty, n } from "../components/ui.jsx";
import { BarChart } from "../components/charts.jsx";
import { PageHeader, Section, Kpi, Tabs, Pager, go } from "../components/layout.jsx";

const BASEMAPS = [["osm", "OSM"], ["satellite", "Satellite"], ["topo", "Topo"]];

export function Dashboard() {
  const [dates, setDates] = useState(null);
  const [date, setDate] = useState(null);
  const [eventClass, setEventClass] = useState("");
  const [flaresOnly, setFlaresOnly] = useState(false);
  const [basemap, setBasemap] = useState("osm");
  const [geo, setGeo] = useState(null);
  const [rows, setRows] = useState(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(10);
  const [classes, setClasses] = useState(null);
  const [recent, setRecent] = useState(null);
  const [level, setLevel] = useState("High");

  useEffect(() => {
    api.dates(14).then((d) => { setDates(d.dates); if (d.dates[0]) setDate(d.dates[0].date); });
    api.classification().then(setClasses).catch(() => setClasses({ by_class: [] }));
  }, []);

  const cls = flaresOnly ? "gas_flare" : eventClass || undefined;

  // Map and table follow the same filters; old markers stay until new arrive.
  useEffect(() => {
    if (!date) return;
    let off = false;
    api.geojson({ date, eventClass: cls, limit: 1200 }).then((g) => !off && setGeo(g));
    return () => { off = true; };
  }, [date, cls]);

  useEffect(() => {
    if (!date) return;
    let off = false;
    api.alerts({ date, eventClass: cls, limit, offset }).then((r) => {
      if (off) return;
      setRows(r.alerts); setTotal(r.total_matching);
    });
    return () => { off = true; };
  }, [date, cls, limit, offset]);

  useEffect(() => {
    if (!date) return;
    api.alerts({ date, level: level || undefined, limit: 6 }).then((r) => setRecent(r));
  }, [date, level]);

  const day = dates?.find((d) => d.date === date);
  const reset = () => { setEventClass(""); setFlaresOnly(false); setOffset(0); };

  const dist = {};
  for (const r of classes?.by_class || []) dist[r.event_class] = (dist[r.event_class] || 0) + Number(r.count);
  const distRows = Object.entries(dist)
    .filter(([k]) => classInfo(k).group === "Industrial")
    .map(([k, v]) => ({ id: k, label: classInfo(k).label, icon: classInfo(k).icon, tone: classInfo(k).tone, count: v }))
    .sort((a, b) => b.count - a.count);

  return (
    <>
      <PageHeader eyebrow="System intelligence" title="Thermal source intelligence"
                  sub="FIRMS detections, persistent thermal sources and source-type assessments" />

      <Section idx="01" title="Operational summary" note={date ? `FIRMS activity for ${date}` : "Loading"}>
        <div class="flex justify-end items-center gap-3 mb-4">
          <span class="label-caps">Observation date</span>
          <select class="field field-mono" value={date || ""} onChange={(e) => { setDate(e.target.value); setOffset(0); }}>
            {!dates && <option>Loading dates…</option>}
            {dates?.map((d) => <option key={d.date} value={d.date}>{d.date} | {Number(d.detections).toLocaleString()} hits</option>)}
          </select>
        </div>
        <div class="grid gap-3 grid-cols-2 xl:grid-cols-4">
          <Kpi label="FIRMS detections" icon="radar" value={day && n(day.detections)} />
          <Kpi label="At known sources" icon="center_focus_strong" value={day && n(day.known)} sub={day && `${n(day.known_places)} distinct places`} />
          <Kpi label="New locations" icon="bolt" value={day && n(day.new_locations)} sub="no 2025 history" />
          <Kpi label="High alerts" icon="local_fire_department" tone="var(--color-high)" value={day && n(day.high)} />
        </div>
      </Section>

      <Section idx="02" title="Spatial object explorer" note="Selected-date detections, typed by source">
        <div class="panel p-4 mb-4 grid gap-3" style="grid-template-columns:repeat(auto-fit,minmax(240px,1fr))">
          <label class="flex flex-col gap-1.5">
            <span class="label-caps">Source classification</span>
            <select class="field" value={eventClass} disabled={flaresOnly}
                    onChange={(e) => { setEventClass(e.target.value); setOffset(0); }}>
              <option value="">All classifications</option>
              {EVENT_CLASSES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
          </label>
          <label class="panel-flat flex items-center justify-center gap-2 cursor-pointer text-[12px] font-extrabold tracking-[0.06em] uppercase">
            <input type="checkbox" checked={flaresOnly} onChange={(e) => { setFlaresOnly(e.target.checked); setOffset(0); }} />
            Likely gas flares only
          </label>
          <button class="btn" onClick={() => go("classification")}>View classification</button>
          <button class="btn btn-primary" onClick={reset}>Reset filters</button>
        </div>

        <div class="panel relative mb-4">
          <div class="absolute top-3 right-3 z-[500] flex border-2 border-black bg-black">
            {BASEMAPS.map(([id, label]) => (
              <button key={id} onClick={() => setBasemap(id)}
                      class="h-7 px-2.5 text-[10px] font-extrabold tracking-[0.06em] uppercase cursor-pointer border-0"
                      style={basemap === id ? "background:#d8f5a9;color:#000" : "background:#000;color:#fff"}>{label}</button>
            ))}
          </div>
          {geo ? <AlertMap geojson={geo} colourBy="class" mode="industrial" basemap={basemap}
                           onSelect={(c) => go(`investigation/${c}`)} />
               : <Loading label="Loading map" />}
          <div class="flex flex-wrap gap-4 px-4 py-3 border-t-2 border-rule">
            {Object.entries(FAMILY_TONE).map(([k, t]) => (
              <span key={k} class="flex items-center gap-2 text-[11px] font-extrabold tracking-[0.06em] uppercase">
                <span class="w-3 h-3 border-2 border-black" style={`background:${t}`} />{k}
              </span>
            ))}
          </div>
        </div>

        <div class="panel">
          <div class="px-4 py-3 border-b-2 border-rule">
            <p class="m-0 text-[14px] font-black tracking-[0.05em] uppercase">Detections on this date</p>
            <p class="m-0 text-[12px] text-muted">Showing {n(rows?.length)} on this page, {n(total)} matching · a place can appear once per satellite pass</p>
          </div>
          <div class="overflow-x-auto">
            {!rows ? <Loading label="Loading sources" /> : rows.length === 0
              ? <Empty title="Nothing matches" body="Try another date or clear the filters." />
              : (
              <table class="tbl" style="min-width:880px">
                <thead><tr><th>Source</th><th>Classification</th><th>Alert</th><th class="num">Score</th><th class="num">FRP MW</th><th>Pass</th><th>Coordinates</th></tr></thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={`${r.cell_id}-${i}`}>
                      <td><button onClick={() => go(`investigation/${r.cell_id}`)} class="mono text-[12px] font-bold underline bg-transparent border-0 cursor-pointer p-0 text-[var(--color-ink)]">CELL_{r.cell_id}</button></td>
                      <td><ClassBadge eventClass={r.event_class} source={r.class_source} confidence={r.class_confidence} /></td>
                      <td><span class="text-[12px] font-extrabold uppercase" style={`color:${LEVEL_COLOURS[r.alert_level] || "inherit"}`}>{r.alert_level}</span></td>
                      <td class="num mono">{r.alert_score}</td>
                      <td class="num mono">{r.frp}</td>
                      <td class="mono text-[12px]">{r.daynight === "N" ? "Night" : "Day"} {String(r.acq_time).padStart(4, "0")}</td>
                      <td><span class="mono text-[12px] mr-2">{r.latitude.toFixed(4)}, {r.longitude.toFixed(4)}</span><MapLink lat={r.latitude} lon={r.longitude} compact /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <Pager offset={offset} limit={limit} total={total} onOffset={setOffset} onLimit={(l) => { setLimit(l); setOffset(0); }} />
        </div>
      </Section>

      <Section idx="03" title="Distribution and alerts" note="Source types and the day's strongest alerts">
        <div class="grid gap-4 items-start" style="grid-template-columns:repeat(auto-fit,minmax(380px,1fr))">
          <div class="panel">
            <div class="px-4 py-3 border-b-2 border-rule">
              <p class="m-0 text-[14px] font-black tracking-[0.05em] uppercase">Industry distribution</p>
              <p class="m-0 text-[12px] text-muted">Industrial source types across all current detections</p>
            </div>
            <div class="p-4">{classes ? <BarChart data={distRows} valueKey="count" labelKey="label" /> : <Loading />}</div>
          </div>
          <div class="panel">
            <div class="px-4 py-3 border-b-2 border-rule flex items-center justify-between gap-2">
              <div>
                <p class="m-0 text-[14px] font-black tracking-[0.05em] uppercase">Recent alerts</p>
                <p class="m-0 text-[12px] text-muted">Strongest scoring detections on {date || "…"}</p>
              </div>
              <button class="btn btn-primary h-8" onClick={() => go("alerts")}>View all</button>
            </div>
            <div class="px-4 pt-3"><Tabs value={level} onChange={setLevel}
              options={[{ label: "All", value: "" }, { label: "High", value: "High" }, { label: "Medium", value: "Medium" }, { label: "Volcano", value: "Natural (volcano)" }]} /></div>
            <div class="p-4 flex flex-col gap-2">
              {!recent ? <Loading /> : recent.alerts.length === 0 ? <Empty title="No alerts at this level" /> : recent.alerts.map((a, i) => (
                <button key={i} onClick={() => go(`investigation/${a.cell_id}`)}
                        class="text-left panel-flat px-3 py-2.5 cursor-pointer bg-[var(--color-panel)] text-[var(--color-ink)]">
                  <div class="flex items-center justify-between gap-2">
                    <span class="text-[12px] font-extrabold uppercase">{classInfo(a.event_class).label}</span>
                    <span class="pill border-black text-[var(--color-ink)]">{a.alert_level}</span>
                  </div>
                  <p class="m-0 mt-1 text-[12px] text-muted leading-[17px]">{a.why}</p>
                  <p class="mono m-0 mt-1 text-[11px]">{a.acq_date} · {a.latitude.toFixed(4)}, {a.longitude.toFixed(4)}</p>
                </button>
              ))}
            </div>
          </div>
        </div>
      </Section>
    </>
  );
}
