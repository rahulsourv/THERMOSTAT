import { useEffect, useState } from "preact/hooks";
import {
  api, EVENT_CLASSES, classInfo, CLASS_SOURCES, FAMILY_TONE,
} from "../api.js";
import { AlertMap } from "../components/AlertMap.jsx";
import {
  Panel, StatTile, Loading, Empty, Icon, ClassBadge, MapLink, n, pct,
} from "../components/ui.jsx";
import {
  BarChart, StackedBar, ScoreBars, ConfidenceHistogram, CAT, fmt,
} from "../components/charts.jsx";

/**
 * SIH26162 stage 2 — what caused each thermal anomaly.
 *
 * The page is ordered the way a reader needs it, not the way the pipeline
 * runs: what did we find, how sure are we, and only then how the model
 * scored. The accuracy panel is deliberately not buried — this classifier
 * is weak at naming specific industries and the page says so in words
 * rather than leaving a reader to infer it from an F1 column.
 */

export function Classification({ selected, onSelect }) {
  const [data, setData] = useState(null);
  const [geojson, setGeojson] = useState(null);
  const [picked, setPicked] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.classification().then(setData).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.geojson({ eventClass: picked || undefined, limit: 1200 })
      .then((geo) => { if (!cancelled) { setGeojson(geo); setLoading(false); } })
      .catch((e) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [picked]);

  if (error) {
    return <Empty icon="cloud_off" title="Could not load classification" body={error} />;
  }
  if (!data) return <Loading label="Loading classification" />;
  if (!data.trained) {
    return (
      <Panel title="Not trained yet">
        <Empty icon="model_training" title="No event classifier found"
               body="Run build_event_labels.py then train_event_classifier.py in ML/." />
      </Panel>
    );
  }

  // The API returns one row per (class, source); fold to one row per class.
  const merged = new Map();
  for (const row of data.by_class) {
    const e = merged.get(row.event_class)
      || { id: row.event_class, count: 0, places: 0, bySource: {} };
    e.count += Number(row.count) || 0;
    e.places += Number(row.places) || 0;
    e.bySource[row.class_source] =
      (e.bySource[row.class_source] || 0) + Number(row.count);
    merged.set(row.event_class, e);
  }

  const rows = [...merged.values()]
    .map((r) => {
      const info = classInfo(r.id);
      return { ...r, label: info.label, icon: info.icon, tone: info.tone,
               group: info.group, blurb: info.blurb };
    })
    .sort((a, b) => b.count - a.count);

  const total = rows.reduce((s, r) => s + r.count, 0) || 1;
  const familyTotal = (name) =>
    rows.filter((r) => r.group === name).reduce((s, r) => s + r.count, 0);

  const sourceTotal = (name) =>
    data.by_class.filter((r) => r.class_source === name)
      .reduce((s, r) => s + Number(r.count), 0);

  const model = data.model || {};
  const perClass = Object.entries(model.per_class || {})
    .map(([k, m]) => ({ label: classInfo(k).label, value: m["f1-score"] ?? 0,
                        support: m.support }))
    .sort((a, b) => b.value - a.value);

  const industrial = familyTotal("Industrial");

  return (
    <>
      {/* ---- What we found ------------------------------------------- */}
      <div class="grid gap-3 mb-3" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
        <StatTile label="Detections typed" icon="category" value={n(total)}
                  sub={`${rows.length} categories`} dot={false} />
        <StatTile label="Industrial" icon="factory" tone={FAMILY_TONE.Industrial}
                  value={n(industrial)} sub={`${pct(industrial / total, 1)} of all heat seen`} />
        <StatTile label="Natural" icon="forest" tone={FAMILY_TONE.Natural}
                  value={n(familyTotal("Natural"))} sub="fires, crops and volcanoes" />
        <StatTile label="Confirmed on the ground" icon="verified" tone="#1baf7a"
                  value={n(sourceTotal("mapped"))}
                  sub="matched a real mapped site" />
        <StatTile label="Named by the model" icon="neurology" tone="#2a78d6"
                  value={n(sourceTotal("predicted"))}
                  sub="unmapped places, high confidence only" />
      </div>

      <div class="grid gap-4 items-start" style="grid-template-columns:minmax(0,1.55fr) minmax(340px,1fr)">
        <div class="flex flex-col gap-4">
          <Panel
            title={picked ? `Map — ${classInfo(picked).label}` : "Where these sources are"}
            subtitle={
              picked
                ? "One category shown. Click its bar again to show everything."
                : "Orange is human industry, green is natural. Click any point for detail and a Google Maps link."
            }
            right={picked && (
              <button class="btn h-7 text-[11px]" onClick={() => setPicked(null)}>
                <Icon name="close" style="font-size:14px" /> Show all
              </button>
            )}
          >
            <div class={loading ? "opacity-50 transition-opacity pointer-events-none" : "transition-opacity"}>
              {geojson
                ? <AlertMap geojson={geojson} colourBy="class" mode="industrial"
                            onSelect={onSelect} selectedCellId={selected} />
                : <Loading label="Loading map" />}
            </div>
            <div class="flex flex-wrap gap-4 px-4 py-3 border-t border-rule">
              {Object.entries(FAMILY_TONE).map(([name, tone]) => (
                <span key={name} class="flex items-center gap-1.5 text-[12px]">
                  <span class="w-3 h-3 rounded-full" style={`background:${tone}`} />
                  <b>{name}</b>
                  <span class="text-muted">{fmt(familyTotal(name))}</span>
                </span>
              ))}
            </div>
          </Panel>

          <Panel
            title="How much of this is actually verified?"
            subtitle="Every type is labelled with where it came from, because a mapped factory and a model guess are not the same claim."
          >
            <div class="p-4">
              <StackedBar segments={[
                { label: "Matched a mapped site", value: sourceTotal("mapped"), tone: CAT.mapped },
                { label: "Model named the type", value: sourceTotal("predicted"), tone: CAT.predicted },
                { label: "Industrial, type unspecified", value: sourceTotal("stage1_only"), tone: "#94631b" },
                { label: "Rule (fires and crops)", value: sourceTotal("rule"), tone: CAT.rule },
                { label: "No history yet", value: sourceTotal("none"), tone: CAT.none },
              ]} />
              <div class="grid gap-2 mt-4" style="grid-template-columns:repeat(auto-fit,minmax(210px,1fr))">
                {Object.entries(CLASS_SOURCES).map(([key, meta]) => (
                  <div key={key} class="flex items-start gap-2">
                    <span class="w-2.5 h-2.5 rounded-[2px] mt-1 shrink-0"
                          style={`background:${meta.tone}`} />
                    <span class="text-[11px] leading-[16px]">
                      <b>{meta.label}</b>
                      <span class="text-muted"> — {meta.hint}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </Panel>

          <Panel
            title="How well can the model name an industry?"
            subtitle="Cross-validated on regions it never saw. Read this before trusting a type."
          >
            <div class="p-4">
              <ScoreBars rows={perClass} threshold={0.5} />
              <div class="mt-5 pt-4 border-t border-rule">
                <p class="label-caps m-0 mb-2">
                  Why most places say “type unknown”
                </p>
                <ConfidenceHistogram bins={data.confidence_histogram || []}
                                     gate={0.9} />
              </div>

              <div class="mt-4 rounded-[8px] bg-wash border border-rule p-3">
                <p class="m-0 text-[12px] font-semibold">What this actually means</p>
                <p class="m-0 mt-1 text-[12px] text-muted leading-[18px]">
                  Telling <b>industrial from natural</b> works well — F1 0.94 for
                  industrial. Telling <b>which industry</b> does not: overall
                  macro-F1 is{" "}
                  <b>{model.macro_f1?.toFixed(2)}</b> against a{" "}
                  {model.baseline_macro_f1?.toFixed(2)} baseline. A power
                  station, a smelter and a quarry all look like steady night-time
                  heat from orbit, and nothing in the satellite signal separates
                  them. That is why a specific type is only published when the
                  model is at least 90% confident, and everything else is
                  reported as “industrial, type unknown”.
                </p>
              </div>
            </div>
          </Panel>
        </div>

        {/* ---- Right column -------------------------------------------- */}
        <div class="flex flex-col gap-4">
          <Panel title="What is burning" subtitle="Click a bar to isolate it on the map">
            <div class="p-4">
              <BarChart data={rows} valueKey="count" labelKey="label"
                        onSelect={setPicked} selected={picked} maxRows={11} />
            </div>
          </Panel>

          <Panel title="What each category means">
            <div class="max-h-[320px] overflow-y-auto">
              {EVENT_CLASSES.filter((c) => merged.has(c.id)).map((c) => (
                <div key={c.id} class="px-4 py-2.5 border-b border-[#f1f5f9]">
                  <span class="flex items-center gap-2">
                    <Icon name={c.icon} style={`font-size:15px;color:${c.tone}`} />
                    <b class="text-[12px]">{c.label}</b>
                    <span class="text-[11px] text-muted ml-auto tabular-nums">
                      {fmt(merged.get(c.id)?.count)}
                    </span>
                  </span>
                  <p class="m-0 mt-1 text-[11px] text-muted leading-[16px]">
                    {c.blurb}
                  </p>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Reference catalogue"
                 subtitle="Every place scored on a full year of 2025 behaviour">
            <div class="p-4">
              <BarChart
                data={(data.reference_places || []).map((r) => ({
                  id: r.event_class,
                  label: classInfo(r.event_class).label,
                  count: Number(r.places),
                }))}
                valueKey="count" labelKey="label" maxRows={10}
              />
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
