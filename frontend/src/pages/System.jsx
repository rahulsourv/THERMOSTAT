import { useEffect, useState } from "preact/hooks";
import { api } from "../api.js";
import { Loading, Empty, Icon, n } from "../components/ui.jsx";
import { PageHeader, Section } from "../components/layout.jsx";
import { ModelReport } from "./ModelReport.jsx";

/** Pipeline health plus the model's report card. */
export function System() {
  const [runs, setRuns] = useState(null);
  useEffect(() => { api.runs(20).then(setRuns).catch(() => setRuns({ runs: [] })); }, []);

  const last = runs?.runs?.[0];
  const fmt = (d) => d ? new Date(d).toLocaleString() : "—";
  const cell = (k, v) => (
    <div class="panel-flat px-3 py-2.5"><span class="label-caps">{k}</span>
      <div class="mono text-[14px] font-bold mt-1 uppercase">{v}</div></div>
  );

  return (
    <>
      <PageHeader eyebrow="System and model telemetry" title="Pipeline operations"
                  sub="Daily FIRMS ingestion, run history and the model report card" />

      <Section idx="01" title="Latest monitoring run">
        {!runs ? <Loading /> : !last ? <Empty title="No runs recorded" /> : (
          <div class="panel p-4 grid gap-3" style="grid-template-columns:repeat(auto-fit,minmax(170px,1fr))">
            {cell("Status", last.status)}
            {cell("Started", fmt(last.started_at))}
            {cell("Duration", `${last.seconds ?? "—"} s`)}
            {cell("Detections", n(last.detections))}
            {cell("High alerts", n(last.high_alerts))}
            {cell("Successes / failures", `${runs.summary?.successes ?? "—"} / ${runs.summary?.failures ?? "—"}`)}
          </div>
        )}
        <div class="panel p-4 mt-4 flex items-start gap-3 flex-wrap">
          <Icon name="schedule" style="font-size:22px" />
          <div class="flex-1 min-w-[260px]">
            <p class="m-0 text-[14px] font-semibold">Runs automatically every day at 05:00 IST</p>
            <p class="m-0 mt-1 text-[13px] text-muted">
              Windows Task Scheduler runs <span class="mono">run_daily.bat</span>, which fetches the last two UTC days
              of FIRMS worldwide, scores them and reloads the database in one transaction. Run it by hand from the
              project folder:
            </p>
            <code class="mono block mt-2 text-[12px] bg-[var(--color-wash)] border border-rule rounded-[8px] p-2.5">run_daily.bat</code>
          </div>
        </div>
      </Section>

      <Section idx="02" title="Run history" note="Latest 20 executions">
        <div class="panel overflow-x-auto">
          {!runs?.runs?.length ? <Empty title="No history" /> : (
            <table class="tbl" style="min-width:720px">
              <thead><tr><th>Run</th><th>Status</th><th>Started</th><th class="num">Seconds</th><th class="num">Detections</th><th class="num">High alerts</th><th>Error</th></tr></thead>
              <tbody>{runs.runs.map((r) => (
                <tr key={r.id}>
                  <td class="mono">#{r.id}</td>
                  <td class="font-semibold text-[12px]" style={`color:${r.status === "success" ? "var(--color-confirmed)" : "var(--color-high)"}`}>{r.status}</td>
                  <td class="mono text-[12px]">{fmt(r.started_at)}</td>
                  <td class="num mono">{r.seconds ?? "—"}</td>
                  <td class="num mono">{n(r.detections)}</td>
                  <td class="num mono">{n(r.high_alerts)}</td>
                  <td class="text-[12px] text-muted whitespace-normal max-w-[260px]">{r.error || "—"}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      </Section>

      <Section idx="03" title="Model report card" note="Measured on held-out regions">
        <ModelReport />
      </Section>
    </>
  );
}
