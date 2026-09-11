import { useEffect, useState } from "preact/hooks";
import { api, classInfo, CLASS_SOURCES } from "../api.js";
import { AlertMap } from "../components/AlertMap.jsx";
import { ClassBadge, MapLink, Loading, Empty, Icon, n, pct } from "../components/ui.jsx";
import { PageHeader, Section, Kpi, go } from "../components/layout.jsx";

/** One source in depth: behaviour over 2025, context, and latest passes. */
export function Investigation({ selected }) {
  const [place, setPlace] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!selected) return;
    setPlace(null); setError(null);
    api.place(selected).then(setPlace).catch((e) => setError(e.message));
  }, [selected]);

  if (!selected) {
    return (
      <div class="panel p-10 text-center max-w-[640px] mx-auto mt-10">
        <Icon name="plagiarism" style="font-size:34px" />
        <h2 class="text-[20px] font-semibold mt-3 mb-2">No thermal source selected</h2>
        <p class="text-[13px] text-muted mb-5 ">
          Select a source on the map, the object list or search to inspect its behaviour and context.
        </p>
        <div class="flex gap-2 justify-center">
          <button class="btn btn-primary" onClick={() => go("dashboard")}>Go to spatial map</button>
          <button class="btn" onClick={() => go("search")}>Search sources</button>
        </div>
      </div>
    );
  }
  if (error) return <Empty icon="error" title="Source not found" body={`Cell ${selected}: ${error}. It may have no 2025 history.`} />;
  if (!place) return <Loading label="Loading source" />;

  const p = place;
  const info = classInfo(p.event_class);
  const src = CLASS_SOURCES[p.class_source] || CLASS_SOURCES.none;
  const geo = { type: "FeatureCollection", features: [{
    type: "Feature", geometry: { type: "Point", coordinates: [p.longitude, p.latitude] },
    properties: { cell_id: p.cell_id, event_class: p.event_class, class_source: p.class_source,
                  alert_level: p.static_probability >= 0.9 ? "High" : "Low", alert_score: Math.round(p.static_probability * 1000) / 10,
                  static_probability: p.static_probability, frp: p.frp_mean?.toFixed(1), why: info.blurb },
  }] };

  return (
    <>
      <button class="btn h-8 mb-4" onClick={() => history.back()}><Icon name="arrow_back" style="font-size:16px" />Back</button>
      <PageHeader eyebrow="Source investigation" title={`Cell ${p.cell_id}`}
                  sub={`${p.latitude.toFixed(5)}, ${p.longitude.toFixed(5)} · 5 km grid cell`}
                  right={<div class="flex gap-2"><MapLink lat={p.latitude} lon={p.longitude} /><MapLink lat={p.latitude} lon={p.longitude} satellite /></div>} />

      <div class="panel p-4 mt-6 flex items-start gap-4 flex-wrap">
        <Icon name={info.icon} style={`font-size:30px;color:${info.tone}`} />
        <div class="flex-1 min-w-[240px]">
          <ClassBadge eventClass={p.event_class} source={p.class_source} confidence={p.class_confidence} />
          <p class="m-0 mt-2 text-[14px] font-semibold">{info.blurb}</p>
          <p class="m-0 mt-1 text-[12px] text-muted">How this was decided: <b>{src.label}</b> — {src.hint}</p>
        </div>
      </div>

      <Section idx="01" title="Behaviour across 2025" note="From every VIIRS detection in this cell">
        <div class="grid gap-3 grid-cols-2 md:grid-cols-3 xl:grid-cols-6">
          <Kpi label="Persistence score" icon="target" value={pct(p.static_probability, 1)} />
          <Kpi label="Active days" icon="calendar_month" value={n(p.active_days)} sub="of 365" />
          <Kpi label="Months active" icon="date_range" value={`${p.months_active}/12`} />
          <Kpi label="Night share" icon="dark_mode" value={pct(p.night_fraction)} />
          <Kpi label="Detections" icon="radar" value={n(p.total_detections)} />
          <Kpi label="Duty cycle" icon="timelapse" value={pct(p.duty_cycle)} />
        </div>
      </Section>

      <Section idx="02" title="Thermal fingerprint and context">
        <div class="grid gap-4 items-start" style="grid-template-columns:minmax(0,1.4fr) minmax(300px,1fr)">
          <div class="panel"><AlertMap geojson={geo} colourBy="class" mode="industrial" basemap="satellite" selectedCellId={p.cell_id} /></div>
          <div class="panel p-4">
            <table class="w-full text-[13px]"><tbody>
              {[["Mean radiative power", `${p.frp_mean?.toFixed(2)} MW`], ["Power variability (σ)", `${p.frp_std?.toFixed(2)} MW`],
                ["Spatial spread", `${p.spread_km?.toFixed(2)} km`],
                ["Nearest volcano", `${p.km_to_volcano?.toFixed(1)} km${p.is_volcanic ? " · volcanic" : ""}`],
                ["Nearest thermal power plant", `${p.km_to_thermal_plant?.toFixed(1)} km${p.near_power_plant ? " · confirmed" : ""}`]]
                .map(([k, v]) => (
                  <tr key={k} class="border-b border-[var(--color-hair)]">
                    <td class="py-2 text-muted font-semibold">{k}</td><td class="py-2 text-right mono">{v}</td>
                  </tr>
                ))}
            </tbody></table>
            <p class="m-0 mt-3 text-[11px] text-muted leading-[16px]">
              Distances are reference context only. They are never model inputs, so the classification stays independent of the registers used to check it.
            </p>
          </div>
        </div>
      </Section>

      <Section idx="03" title="Latest satellite passes" note={`${p.recent_detections?.length || 0} recent detections`}>
        <div class="panel overflow-x-auto">
          {!p.recent_detections?.length ? <Empty title="No recent detections" body="Not seen in the current two-day window." /> : (
            <table class="tbl" style="min-width:620px">
              <thead><tr><th>Date</th><th>Time UTC</th><th>Pass</th><th class="num">FRP MW</th><th>Confidence</th><th>Alert</th><th class="num">Score</th></tr></thead>
              <tbody>{p.recent_detections.map((d, i) => (
                <tr key={i}>
                  <td class="mono">{d.acq_date}</td><td class="mono">{String(d.acq_time).padStart(4, "0")}</td>
                  <td>{d.daynight === "N" ? "Night" : "Day"}</td><td class="num mono">{d.frp}</td>
                  <td class="mono uppercase">{d.confidence}</td><td class="font-semibold text-[12px]">{d.alert_level}</td>
                  <td class="num mono">{d.alert_score}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      </Section>
    </>
  );
}
