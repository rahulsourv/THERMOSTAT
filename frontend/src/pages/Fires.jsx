import { useEffect, useState } from "preact/hooks";
import { api } from "../api.js";
import { AlertMap } from "../components/AlertMap.jsx";
import {
  Panel, StatTile, Pill, Segmented, Loading, Empty, Icon, MapLink,
  SEMANTIC, n,
} from "../components/ui.jsx";

const BANDS = [
  { label: "All", value: 0 },
  { label: "50+ FRP", value: 50, tone: SEMANTIC.Moderate },
  { label: "300+ FRP", value: 300, tone: SEMANTIC.Large },
];

export function Fires() {
  const [geojson, setGeojson] = useState(null);
  const [fires, setFires] = useState(null);
  const [totals, setTotals] = useState(null);
  const [minFrp, setMinFrp] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      api.firesGeojson({ minFrp, limit: 1600 }),
      api.fires({ minFrp, limit: 80 }),
    ]).then(([geo, list]) => {
      if (cancelled) return;
      setGeojson(geo);
      setFires(list.fires);
      setTotals(list.totals);
      setLoading(false);
    });

    return () => { cancelled = true; };
  }, [minFrp]);

  return (
    <>
      <div class="grid gap-3 mb-3" style="grid-template-columns:repeat(auto-fit,minmax(210px,1fr))">
        <StatTile label="Fire events" icon="local_fire_department"
          value={n(totals?.events)}
          sub={`${n(totals?.detections)} detections grouped`} dot={false} />
        <StatTile label="Large" icon="whatshot" tone={SEMANTIC.Large}
          value={n(totals?.large)} sub="300+ total FRP" />
        <StatTile label="Moderate" icon="whatshot" tone={SEMANTIC.Moderate}
          value={n(totals?.moderate)} sub="50–300 total FRP" />
        <StatTile label="Small" icon="whatshot" tone={SEMANTIC.Small}
          value={n(totals?.small)} sub="under 50 total FRP" />
      </div>

      <div class="grid gap-4 items-start" style="grid-template-columns:minmax(0,1.6fr) minmax(340px,1fr)">
        <Panel
          title="Fire events — circle size shows total intensity"
          subtitle="Detections grouped on an 11 km grid, ranked by summed radiative power"
          right={<Segmented options={BANDS} value={minFrp} onChange={setMinFrp} />}
        >
          <div class={loading ? "opacity-50 transition-opacity pointer-events-none" : "transition-opacity"}>
            {geojson
              ? <AlertMap geojson={geojson} mode="fires" />
              : <Loading label="Loading map" />}
          </div>
        </Panel>

        <div class="flex flex-col gap-4">
          <Panel title="Biggest fires now"
                 subtitle="Ranked by total fire radiative power">
            <div class="max-h-[430px] overflow-y-auto">
              {!fires ? (
                <Loading label="Loading fires" />
              ) : fires.length === 0 ? (
                <Empty icon="filter_alt_off" title="No fires match this filter" />
              ) : (
                fires.map((f, i) => (
                  <div key={i}
                       class="px-4 py-2.5 border-b border-[#f1f5f9]"
                       style={`border-left:3px solid ${SEMANTIC[f.severity]}`}>
                    <div class="flex items-baseline justify-between gap-2 flex-wrap">
                      <span class="text-[13px] font-semibold">
                        {Number(f.latitude).toFixed(1)}, {Number(f.longitude).toFixed(1)}
                      </span>
                      <div class="flex items-center gap-2">
                        <span class="text-[13px] font-semibold"
                              style={`color:${SEMANTIC[f.severity]}`}>
                          {n(f.total_frp, 1)} FRP
                        </span>
                        <Pill tone={SEMANTIC[f.severity]}>{f.severity}</Pill>
                      </div>
                    </div>
                    <p class="text-[12px] text-muted m-0 mt-1 leading-[17px]">
                      {f.why}
                    </p>
                    <div class="mt-1.5">
                      <MapLink lat={Number(f.latitude)} lon={Number(f.longitude)}
                               compact />
                    </div>
                  </div>
                ))
              )}
            </div>
          </Panel>

          {/* The honesty panel. This tab is the one most likely to be
              misread as a forecast, so the disclaimer is not a footnote. */}
          <Panel title="What this tab is">
            <div class="p-4 flex flex-col gap-3">
              <div class="rounded-[8px] p-3 text-[12px] leading-[18px] bg-wash border-l-[3px]"
                   style="border-color:#2563eb">
                These are fires the satellite <b>already saw burning</b>.
                Detections with a low static-source probability are grouped
                into events on an 11 km grid and ranked by total intensity.
              </div>
              <div class="rounded-[8px] p-3 text-[12px] leading-[18px]"
                   style="background:#fef2f2;border-left:3px solid #dc2626">
                <b>This is not a forecast.</b> Predicting where a fire will
                start needs weather, fuel dryness and vegetation data that
                ThermoStats does not use.
              </div>
              <div class="flex items-start gap-2 text-[11px] text-muted">
                <Icon name="info" style="font-size:14px;margin-top:1px" />
                <span>
                  Fires burn hotter but briefly; industrial sources burn
                  weaker but constantly. That difference is what the model
                  separates.
                </span>
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
