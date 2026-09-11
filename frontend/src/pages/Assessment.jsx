import { useEffect, useState } from "preact/hooks";
import { api, classInfo, FAMILY_TONE } from "../api.js";
import { MapLink, Loading, Empty, n } from "../components/ui.jsx";
import { PageHeader, Section, Kpi, go } from "../components/layout.jsx";

// Coarse world regions from coordinates. Our data is global with no admin
// boundaries attached, so this is an approximate grouping and is labelled so.
// Order matters: the first box that contains a point wins.
const REGIONS = [
  ["India", 6, 36, 68, 98], ["Middle East", 12, 42, 34, 63],
  ["China & East Asia", 18, 54, 98, 146], ["Southeast Asia", -11, 18, 92, 141],
  ["Russia & Central Asia", 42, 78, 45, 180], ["Europe", 36, 72, -25, 45],
  ["Africa", -35, 37, -18, 52], ["North America", 15, 72, -170, -50],
  ["South America", -56, 15, -82, -34], ["Oceania", -48, -10, 110, 180],
];
const regionOf = (lat, lon) =>
  (REGIONS.find(([, s, nn, w, e]) => lat >= s && lat <= nn && lon >= w && lon <= e) || ["Other"])[0];

export function Assessment() {
  const [summary, setSummary] = useState(null);
  const [geo, setGeo] = useState(null);
  const [cls, setCls] = useState(null);
  const [unmatched, setUnmatched] = useState(null);

  useEffect(() => {
    api.summary().then(setSummary);
    api.geojson({ limit: 5000 }).then(setGeo);
    api.classification().then(setCls).catch(() => setCls({ by_class: [] }));
    api.alerts({ known: false, limit: 30 }).then(setUnmatched);
  }, []);

  const t = summary?.totals;
  const regions = {};
  for (const f of geo?.features || []) {
    const [lon, lat] = f.geometry.coordinates;
    const r = regionOf(lat, lon);
    regions[r] = (regions[r] || 0) + 1;
  }
  const regionRows = Object.entries(regions).sort((a, b) => b[1] - a[1]);
  const regionMax = regionRows[0]?.[1] || 1;

  const fam = { Industrial: 0, Natural: 0, Unresolved: 0 };
  for (const r of cls?.by_class || []) fam[classInfo(r.event_class).group] += Number(r.count);
  const famTotal = Object.values(fam).reduce((a, b) => a + b, 0) || 1;

  return (
    <>
      <PageHeader eyebrow="Event assessment" title="Event assessment & monitoring"
                  sub="How today's detections match known sources, and which need ground verification" />

      <Section idx="01" title="Satellite monitoring overview" note="Current two-day FIRMS window">
        <div class="grid gap-3 grid-cols-2 xl:grid-cols-4">
          <Kpi label="Total detections" icon="radar" value={t && n(t.total_alerts)} />
          <Kpi label="Matched to known sources" icon="link" tone="var(--color-confirmed)" value={t && n(t.known_places)} sub="place has 2025 history" />
          <Kpi label="Unmatched detections" icon="link_off" tone="var(--color-high)" value={t && n(t.new_locations)} sub="no history — verify" />
          <Kpi label="Reference places" icon="database" value={t && n(t.places_in_reference)} />
        </div>
      </Section>

      <Section idx="02" title="Regional distribution assessment" note="Distinct active places, approximate regions">
        <div class="grid gap-4 items-start" style="grid-template-columns:repeat(auto-fit,minmax(360px,1fr))">
          <div class="panel p-4">
            <p class="label-caps m-0 mb-3">Active thermal sources by region</p>
            {!geo ? <Loading /> : regionRows.map(([name, count]) => (
              <div key={name} class="mb-2.5">
                <div class="flex justify-between text-[12px] font-semibold mb-1">
                  <span>{name}</span><span class="mono">{n(count)}</span>
                </div>
                <div class="h-3 border border-rule bg-[var(--color-wash)]">
                  <div class="h-full bg-[var(--color-ink)]" style={`width:${(count / regionMax) * 100}%`} />
                </div>
              </div>
            ))}
            {geo && <p class="mono m-0 mt-3 text-[12px]">{n(geo.features.length)} places total</p>}
          </div>
          <div class="panel p-4">
            <p class="label-caps m-0 mb-3">Industrial vs natural</p>
            {!cls ? <Loading /> : Object.entries(fam).map(([k, v]) => (
              <div key={k} class="mb-3">
                <div class="flex justify-between text-[12px] font-semibold mb-1">
                  <span>{k}</span><span class="mono">{((v / famTotal) * 100).toFixed(1)}% · {n(v)}</span>
                </div>
                <div class="h-4 border border-rule bg-[var(--color-wash)]">
                  <div class="h-full" style={`width:${(v / famTotal) * 100}%;background:${FAMILY_TONE[k]}`} />
                </div>
              </div>
            ))}
            <p class="m-0 mt-2 text-[12px] text-muted">Share of current detections by source family.</p>
          </div>
        </div>
      </Section>

      <Section idx="03" title="Unmatched satellite detections" note="New locations requiring ground verification">
        <div class="panel">
          {!unmatched ? <Loading /> : unmatched.alerts.length === 0 ? <Empty title="Every detection matched a known place" /> : (
            <div class="divide-y divide-[var(--color-hair)]">
              {unmatched.alerts.map((a, i) => (
                <div key={i} class="px-4 py-3 flex items-center gap-4 flex-wrap">
                  <span class="mono text-[12px] font-bold min-w-[210px]">FIRMS #{a.acq_date}_{String(a.acq_time).padStart(4, "0")}</span>
                  <span class="mono text-[12px] min-w-[200px]">LAT {a.latitude.toFixed(4)}° · LON {a.longitude.toFixed(4)}°</span>
                  <span class="mono text-[12px]">{a.frp} MW · {a.daynight === "N" ? "night" : "day"}</span>
                  <span class="ml-auto flex gap-2"><MapLink lat={a.latitude} lon={a.longitude} compact /></span>
                </div>
              ))}
            </div>
          )}
          <div class="px-4 py-3 border-t border-rule flex justify-between items-center">
            <span class="text-[12px] text-muted">Showing the 30 strongest of {n(unmatched?.total_matching)}</span>
            <button class="btn h-8" onClick={() => go("alerts")}>Open alerts</button>
          </div>
        </div>
      </Section>
    </>
  );
}
