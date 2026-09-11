import { useEffect, useState } from "preact/hooks";
import { api, classInfo, LEVEL_COLOURS } from "../api.js";
import { ClassBadge, MapLink, Loading, Empty, n } from "../components/ui.jsx";
import { PageHeader, Section, Tabs, Pager, go } from "../components/layout.jsx";

const POLL_MS = 30000;

/** Live alert stream, polled every 30 s, filterable by level. */
export function Alerts() {
  const [summary, setSummary] = useState(null);
  const [level, setLevel] = useState("");
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(25);
  const [data, setData] = useState(null);
  const [updated, setUpdated] = useState(null);

  useEffect(() => { api.summary().then(setSummary); }, []);

  useEffect(() => {
    let off = false;
    const load = () => api.alerts({ level: level || undefined, limit, offset }).then((r) => {
      if (off) return;
      setData(r); setUpdated(new Date());
    });
    load();
    const id = setInterval(load, POLL_MS);
    return () => { off = true; clearInterval(id); };
  }, [level, limit, offset]);

  const lv = (k) => summary?.by_level.find((r) => r.alert_level === k)?.count ?? 0;
  const total = summary?.totals.total_alerts ?? 0;

  return (
    <>
      <PageHeader eyebrow="Alerts operations center" title="Alerts"
                  sub="High-priority thermal source events from the current satellite window" />
      <Section idx="01" title="Active alerts stream"
               note={data ? `${n(data.total_matching)} alerts · polling 30s · updated ${updated?.toLocaleTimeString()}` : "Loading"}>
        <div class="mb-4">
          <Tabs value={level} onChange={(v) => { setLevel(v); setOffset(0); }}
                options={[{ label: "All categories", value: "", count: total }, { label: "High", value: "High", count: lv("High") },
                          { label: "Medium", value: "Medium", count: lv("Medium") }, { label: "Low", value: "Low", count: lv("Low") },
                          { label: "Volcano", value: "Natural (volcano)", count: lv("Natural (volcano)") }]} />
        </div>
        <div class="panel">
          {!data ? <Loading /> : data.alerts.length === 0 ? <Empty title="No alerts in this category" /> : (
            <div class="divide-y-2 divide-[var(--color-hair)]">
              {data.alerts.map((a, i) => (
                <div key={`${a.cell_id}-${i}`} class="px-4 py-3.5 grid gap-3 items-start"
                     style="grid-template-columns:minmax(0,1fr) auto">
                  <div class="min-w-0">
                    <div class="flex items-center gap-2 flex-wrap mb-1.5">
                      <span class="pill" style={`color:${LEVEL_COLOURS[a.alert_level] || "inherit"};border-color:currentColor`}>{a.alert_level}</span>
                      <span class="text-[13px] font-black uppercase tracking-[0.04em]">{classInfo(a.event_class).label}</span>
                      <span class="mono text-[11px] text-muted">score {a.alert_score}</span>
                    </div>
                    <p class="m-0 text-[13px] leading-[19px]">{a.why}</p>
                    <p class="mono m-0 mt-1.5 text-[11px] text-muted">
                      {a.acq_date} {String(a.acq_time).padStart(4, "0")} UTC · {a.latitude.toFixed(4)}, {a.longitude.toFixed(4)} · {a.frp} MW
                    </p>
                    <div class="mt-2"><ClassBadge eventClass={a.event_class} source={a.class_source} confidence={a.class_confidence} /></div>
                  </div>
                  <div class="flex flex-col gap-2 items-end">
                    <button class="btn btn-primary h-8" onClick={() => go(`investigation/${a.cell_id}`)}>Investigate</button>
                    <MapLink lat={a.latitude} lon={a.longitude} compact />
                  </div>
                </div>
              ))}
            </div>
          )}
          {data && <Pager offset={offset} limit={limit} total={data.total_matching} onOffset={setOffset}
                          onLimit={(l) => { setLimit(l); setOffset(0); }} />}
        </div>
      </Section>
    </>
  );
}
