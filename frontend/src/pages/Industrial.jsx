import { useEffect, useState } from "preact/hooks";
import { api } from "../api.js";
import { AlertMap } from "../components/AlertMap.jsx";
import {
  Panel, StatTile, Pill, Segmented, Toggle, Loading, Empty, Icon,
  ClassBadge, MapLink, SEMANTIC, n, pct,
} from "../components/ui.jsx";

const LEVELS = [
  { label: "High", value: "High", tone: SEMANTIC.High },
  { label: "Medium", value: "Medium", tone: SEMANTIC.Medium },
  { label: "Low", value: "Low", tone: SEMANTIC.Low },
  { label: "Volcano", value: "Natural (volcano)", tone: SEMANTIC["Natural (volcano)"] },
];

/** One row in the alert feed. The explanation line is the point of it. */
function AlertRow({ a, selected, onSelect }) {
  const tone = a.near_power_plant
    ? SEMANTIC.confirmed
    : a.is_volcanic
    ? SEMANTIC["Natural (volcano)"]
    : SEMANTIC.muted;

  const status = a.near_power_plant
    ? "Confirmed"
    : a.is_volcanic
    ? "Natural"
    : "Unconfirmed";

  return (
    <div
      onClick={() => onSelect(a.cell_id)}
      class="px-4 py-2.5 border-b border-[#f1f5f9] cursor-pointer transition-colors"
      style={
        selected
          ? `background:#f8fafc;border-left:3px solid ${SEMANTIC[a.alert_level] || SEMANTIC.muted}`
          : "border-left:3px solid transparent"
      }
    >
      <div class="flex items-baseline justify-between gap-2 flex-wrap">
        <span class="text-[13px] font-semibold">
          {a.latitude.toFixed(3)}, {a.longitude.toFixed(3)}
        </span>
        <div class="flex items-center gap-2">
          <span
            class="text-[13px] font-semibold"
            style={`color:${SEMANTIC[a.alert_level] || SEMANTIC.muted}`}
          >
            {a.alert_score}/100
          </span>
          <Pill tone={tone}>{status}</Pill>
        </div>
      </div>
      {a.event_class && (
        <div class="mt-1.5 flex items-center gap-2 flex-wrap">
          <ClassBadge eventClass={a.event_class} source={a.class_source}
                      confidence={a.class_confidence} />
          <MapLink lat={a.latitude} lon={a.longitude} compact />
        </div>
      )}
      <p class="text-[12px] text-muted m-0 mt-1 leading-[17px]">{a.why}</p>
    </div>
  );
}

export function Industrial({ selected, onSelect, onOpenPlace }) {
  const [summary, setSummary] = useState(null);
  const [geojson, setGeojson] = useState(null);
  const [alerts, setAlerts] = useState(null);
  const [total, setTotal] = useState(0);
  const [level, setLevel] = useState("High");
  const [confirmedOnly, setConfirmedOnly] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => { api.summary().then(setSummary); }, []);

  // The old data deliberately stays on screen while new data loads.
  // Blanking it would unmount the map and lose the analyst's viewport.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      api.geojson({ level, limit: 900 }),
      api.alerts({ level, limit: 80, confirmedOnly }),
    ]).then(([geo, list]) => {
      if (cancelled) return;
      setGeojson(geo);
      setAlerts(list.alerts);
      setTotal(list.total_matching);
      setLoading(false);
    });

    // Guards against a slow earlier request landing after a newer one.
    return () => { cancelled = true; };
  }, [level, confirmedOnly]);

  const lv = (name) =>
    summary?.by_level.find((r) => r.alert_level === name) || {};
  const confirmed = summary
    ? summary.by_level.reduce((t, r) => t + (r.confirmed || 0), 0)
    : null;

  return (
    <>
      <div class="grid gap-3 mb-3" style="grid-template-columns:repeat(auto-fit,minmax(210px,1fr))">
        <StatTile label="Total detections" icon="sensors"
          value={n(summary?.totals.total_alerts)}
          sub={`${n(summary?.totals.new_locations)} at new locations`} dot={false} />
        <StatTile label="High alerts" icon="warning" tone={SEMANTIC.High}
          value={n(lv("High").count)} sub="persistent static sources" />
        <StatTile label="Confirmed" icon="verified" tone={SEMANTIC.confirmed}
          value={n(confirmed)} sub="within 2 km of a power plant" />
        <StatTile label="Volcanoes" icon="volcano" tone={SEMANTIC["Natural (volcano)"]}
          value={n(lv("Natural (volcano)").count)} sub="natural, filtered out" />
        <StatTile label="Reference places" icon="database"
          value={n(summary?.totals.places_in_reference)}
          sub="scored on 2025 behaviour" dot={false} />
      </div>

      <div class="grid gap-4 items-start" style="grid-template-columns:minmax(0,1.6fr) minmax(340px,1fr)">
        <Panel
          title="Map — one marker per place"
          right={<Segmented options={LEVELS} value={level} onChange={setLevel} />}
        >
          <div class={loading ? "opacity-50 transition-opacity pointer-events-none" : "transition-opacity"}>
            {geojson
              ? <AlertMap geojson={geojson} onSelect={onSelect}
                          selectedCellId={selected} mode="industrial" />
              : <Loading label="Loading map" />}
          </div>
        </Panel>

        <div class="flex flex-col gap-4">
          <Panel
            title="Alerts"
            subtitle={`${n(total)} matching this filter`}
            right={
              <Toggle checked={confirmedOnly} onChange={setConfirmedOnly}
                      label="Confirmed only" />
            }
          >
            <div class="max-h-[430px] overflow-y-auto">
              {!alerts ? (
                <Loading label="Loading alerts" />
              ) : alerts.length === 0 ? (
                <Empty icon="filter_alt_off" title="No alerts match"
                       body="Try turning off 'Confirmed only', or pick a different level." />
              ) : (
                alerts.map((a, i) => (
                  <AlertRow key={`${a.cell_id}-${i}`} a={a}
                            selected={a.cell_id === selected}
                            onSelect={onSelect} />
                ))
              )}
            </div>
            <div class="flex items-center justify-between gap-2 px-4 py-2.5 border-t border-rule">
              <span class="text-[11px] text-muted">
                Showing {n(alerts?.length)} of {n(total)}
              </span>
              <button class="btn h-7 text-[11px]"
                      onClick={() => onOpenPlace(selected)}
                      disabled={!selected}
                      style={!selected ? "opacity:.45;cursor:not-allowed" : ""}>
                <Icon name="open_in_new" style="font-size:14px" />
                Open place detail
              </button>
            </div>
          </Panel>

          <Panel title="Selection">
            {selected ? (
              <SelectionCard cellId={selected} onOpenPlace={onOpenPlace} />
            ) : (
              <Empty
                title="Click a point on the map or an alert"
                body="Opens the full 2025 behaviour profile for that 5 km place, with the evidence behind its score."
              />
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}

function SelectionCard({ cellId, onOpenPlace }) {
  const [place, setPlace] = useState(null);

  useEffect(() => {
    setPlace(null);
    api.place(cellId).then(setPlace).catch(() => setPlace({ error: true }));
  }, [cellId]);

  if (!place) return <Loading label="Loading place" />;
  if (place.error) return <Empty title="Could not load this place" />;

  const tone = place.near_power_plant
    ? SEMANTIC.confirmed
    : place.is_volcanic
    ? SEMANTIC["Natural (volcano)"]
    : SEMANTIC.muted;

  const facts = [
    ["Model probability", pct(place.static_probability, 1)],
    ["Active days", `${place.active_days} / 365`],
    ["Months active", `${place.months_active} / 12`],
    ["At night", pct(place.night_fraction)],
    ["Detections", n(place.total_detections)],
    ["Spread", `${place.spread_km?.toFixed(2)} km`],
  ];

  return (
    <div class="p-4">
      <div class="text-[15px] font-semibold mb-2">
        {place.latitude.toFixed(4)}, {place.longitude.toFixed(4)}
      </div>
      <div class="grid grid-cols-2 gap-x-4 gap-y-1.5 mb-3">
        {facts.map(([k, v]) => (
          <div key={k} class="flex justify-between gap-2 text-[12px]">
            <span class="text-muted">{k}</span>
            <span class="font-medium">{v}</span>
          </div>
        ))}
      </div>
      <div class="rounded-[8px] p-2.5 text-[12px] leading-[17px]"
           style={`background:${tone}0f;border-left:3px solid ${tone}`}>
        {place.verdict}
      </div>
      <button class="btn btn-primary w-full mt-3 justify-center"
              onClick={() => onOpenPlace(cellId)}>
        View full profile
      </button>
    </div>
  );
}
