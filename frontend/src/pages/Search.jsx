import { useEffect, useMemo, useState } from "preact/hooks";
import { api, classInfo } from "../api.js";
import { ClassBadge, MapLink, Loading, Empty, Icon } from "../components/ui.jsx";
import { PageHeader, Tabs, go } from "../components/layout.jsx";

const FAMILIES = [
  { label: "All", value: "" }, { label: "Industrial", value: "Industrial" },
  { label: "Natural", value: "Natural" }, { label: "Unresolved", value: "Unresolved" },
];

/**
 * Search the current detections by cell id, coordinates, or source type.
 * "lat, lon" searches a 1-degree box around the point server-side; anything
 * else filters the loaded catalogue by id or class name.
 */
export function Search() {
  const [q, setQ] = useState("");
  const [family, setFamily] = useState("");
  const [data, setData] = useState(null);

  const coords = q.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);

  useEffect(() => {
    let off = false;
    const t = setTimeout(() => {
      const bbox = coords
        ? `${+coords[2] - 0.5},${+coords[1] - 0.5},${+coords[2] + 0.5},${+coords[1] + 0.5}` : undefined;
      setData(null);
      api.alerts({ limit: 400, bbox }).then((r) => !off && setData(r));
    }, 300);
    return () => { off = true; clearTimeout(t); };
  }, [coords ? coords[0] : ""]);

  const results = useMemo(() => {
    if (!data) return null;
    const seen = new Set();
    const text = coords ? "" : q.trim().toLowerCase();
    return data.alerts.filter((a) => {
      if (seen.has(a.cell_id)) return false;
      const info = classInfo(a.event_class);
      if (family && info.group !== family) return false;
      if (text && !String(a.cell_id).includes(text) && !info.label.toLowerCase().includes(text)
          && !(a.event_class || "").includes(text)) return false;
      seen.add(a.cell_id);
      return true;
    });
  }, [data, q, family]);

  return (
    <>
      <PageHeader eyebrow="Explorer & discovery" title="Search & discovery"
                  sub="Find thermal sources by cell id, coordinates or source type" />
      <div class="panel p-4 mt-6 mb-4 flex flex-col gap-3">
        <div class="flex items-center gap-2">
          <Icon name="search" style="font-size:22px" />
          <input class="field flex-1 h-11 text-[15px]" value={q} onInput={(e) => setQ(e.target.value)}
                 placeholder='Try "gas flare", "32085930" or "21.10, 72.64"' />
        </div>
        <Tabs options={FAMILIES} value={family} onChange={setFamily} />
      </div>

      {!results ? <Loading label="Fetching thermal sources" />
        : results.length === 0 ? <Empty title="No sources match" body="Search by cell id, a class such as 'power plant', or 'lat, lon'." />
        : (
        <>
          <p class="label-caps mb-3">{results.length} sources{coords ? " within about 50 km" : ""}</p>
          <div class="grid gap-3" style="grid-template-columns:repeat(auto-fill,minmax(280px,1fr))">
            {results.slice(0, 120).map((a) => (
              <div key={a.cell_id} class="panel p-4 flex flex-col gap-2">
                <div class="flex items-center justify-between gap-2">
                  <span class="mono text-[13px] font-bold">CELL_{a.cell_id}</span>
                  <span class="text-[11px] font-semibold">{a.alert_level}</span>
                </div>
                <ClassBadge eventClass={a.event_class} source={a.class_source} confidence={a.class_confidence} />
                <p class="m-0 text-[12px] text-muted leading-[17px] min-h-[34px]">{a.why}</p>
                <p class="mono m-0 text-[11px]">{a.latitude.toFixed(4)}, {a.longitude.toFixed(4)} · score {a.alert_score}</p>
                <div class="flex gap-2 mt-1">
                  <button class="btn btn-primary h-8 flex-1" onClick={() => go(`investigation/${a.cell_id}`)}>Investigate</button>
                  <MapLink lat={a.latitude} lon={a.longitude} />
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
