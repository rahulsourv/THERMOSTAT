import { useEffect, useState } from "preact/hooks";
import { api, classInfo } from "../api.js";
import { Panel, StatTile, Loading, Empty, Icon, n, pct } from "../components/ui.jsx";
import { BarChart, ScoreBars } from "../components/charts.jsx";

/**
 * The model's report card - every number measured, none typed in.
 *
 * Everything on this page is read from the JSON the training scripts write
 * (/api/metrics), so it cannot drift from what was actually measured. The page
 * is deliberately candid about Stage 2b: a confusion matrix that is mostly
 * off-diagonal is the finding, and hiding it would misrepresent the system.
 */

/** 2x2 confusion matrix for the binary persistence model. */
function BinaryMatrix({ m }) {
  if (!m) return <Empty title="No confusion matrix" body="Run freeze_stage1_m2_baseline.py." />;
  const cell = (value, correct, label) => (
    <div
      class="rounded-[8px] p-3 flex flex-col justify-center"
      style={`background:${correct ? "#0f8a3d1a" : "#c0392f14"};
              border:1px solid ${correct ? "#0f8a3d40" : "#c0392f30"}`}
    >
      <span class="label-caps">{label}</span>
      <span class="text-[22px] font-semibold tabular-nums mt-0.5"
            style={`color:${correct ? "#0f8a3d" : "#c0392f"}`}>
        {n(value)}
      </span>
    </div>
  );
  return (
    <div>
      <div class="grid gap-2" style="grid-template-columns:auto 1fr 1fr">
        <span />
        <span class="label-caps text-center">Predicted: not industrial</span>
        <span class="label-caps text-center">Predicted: industrial</span>

        <span class="label-caps self-center pr-2">Actually not</span>
        {cell(m.tn, true, "True negative")}
        {cell(m.fp, false, "False positive")}

        <span class="label-caps self-center pr-2">Actually industrial</span>
        {cell(m.fn, false, "Missed")}
        {cell(m.tp, true, "Found")}
      </div>
      <div class="grid gap-3 mt-3" style="grid-template-columns:repeat(4,1fr)">
        {[["Precision", m.precision], ["Recall", m.recall],
          ["Specificity", m.specificity], ["F1", m.f1]].map(([k, v]) => (
          <div key={k}>
            <span class="label-caps">{k}</span>
            <div class="text-[16px] font-semibold tabular-nums">
              {k === "F1" ? v.toFixed(3) : pct(v, 1)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** NxN heat grid: diagonal (correct) in green, confusion in red. */
function MultiMatrix({ labels, rows }) {
  if (!labels?.length) return <Empty title="No confusion matrix" />;
  const max = Math.max(...rows.flat(), 1);
  const colTotals = labels.map((_, j) => rows.reduce((s, r) => s + r[j], 0));
  return (
    <div class="overflow-x-auto">
      <table class="tbl" style="min-width:560px">
        <thead>
          <tr>
            <th class="text-left">truth ↓ / predicted →</th>
            {labels.map((l) => <th key={l} class="num text-[10px]">{classInfo(l).label}</th>)}
            <th class="num text-[10px]">Recall</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const total = row.reduce((s, v) => s + v, 0) || 1;
            return (
              <tr key={labels[i]}>
                <td class="text-[11px] font-semibold whitespace-nowrap">{classInfo(labels[i]).label}</td>
                {row.map((value, j) => {
                  const correct = i === j;
                  const tone = correct ? "#0f8a3d" : "#c0392f";
                  const alpha = Math.round((value / max) * 55).toString(16).padStart(2, "0");
                  return (
                    <td key={j} class="num text-[11px] font-semibold"
                        style={`background:${tone}${alpha};color:${value ? tone : "#94a3b8"}`}>
                      {correct ? `[${value}]` : value}
                    </td>
                  );
                })}
                <td class="num text-[11px] font-semibold">{pct(row[i] / total)}</td>
              </tr>
            );
          })}
          <tr>
            <td class="text-[11px] text-muted">Precision</td>
            {labels.map((_, j) => (
              <td key={j} class="num text-[11px] text-muted">
                {pct(rows[j][j] / (colTotals[j] || 1))}
              </td>
            ))}
            <td />
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function ModelReport() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [threshold, setThreshold] = useState("0.5");

  useEffect(() => {
    api.metrics().then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <Empty icon="cloud_off" title="Could not load metrics" body={error} />;
  if (!data) return <Loading label="Loading model report" />;

  const m2 = data.stage1_m2 || {};
  const disc = m2.discrimination || {};
  const cal = m2.calibration || {};
  const conf = data.stage1_m2_confusion || {};
  const s2 = data.stage2 || {};
  const db = data.dbscan || {};
  const osm = db.osm_validation || {};

  const perClass = Object.entries(s2.per_class || {})
    .map(([k, v]) => ({ label: classInfo(k).label, value: v["f1-score"] ?? 0, support: v.support }))
    .sort((a, b) => b.value - a.value);

  const industries = Object.entries(osm.by_industry || {}).map(([k, v]) => ({
    id: k, label: k.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()), count: v,
  })).sort((a, b) => b.count - a.count);

  return (
    <>
      <div class="grid gap-3 mb-3" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
        <StatTile label="Stage 1 PR-AUC" icon="target" tone="#2a78d6"
          value={disc.pr_auc_mean?.toFixed(3) ?? "—"}
          sub={`± ${disc.pr_auc_std?.toFixed(3) ?? "—"} over held-out regions`} />
        <StatTile label="Precision @ 100" icon="verified" tone="#0f8a3d"
          value={disc.prec_at_100 != null ? pct(disc.prec_at_100) : "—"}
          sub="top 100 predictions that are real" />
        <StatTile label="Independent check" icon="bolt" tone="#d97706"
          value={disc.independent_wri?.lift500 != null ? `${disc.independent_wri.lift500}×` : "—"}
          sub="WRI power plants vs chance, never trained on" />
        <StatTile label="DBSCAN on real industry" icon="hub" tone="#0f8a3d"
          value={osm.confirmed_pct_of_testable != null ? `${osm.confirmed_pct_of_testable}%` : "—"}
          sub={`${osm.clusters_confirmed ?? "—"} of ${db.clusters ?? "—"} clusters confirmed by OSM`} />
        <StatTile label="Stage 2b macro-F1" icon="category" tone="#c0392f"
          value={s2.macro_f1?.toFixed(3) ?? "—"}
          sub={`baseline ${s2.baseline_macro_f1?.toFixed(3) ?? "—"} — industry type is weak`} />
      </div>

      <div class="grid gap-4 items-start" style="grid-template-columns:minmax(0,1.3fr) minmax(340px,1fr)">
        <div class="flex flex-col gap-4">
          <Panel
            title="Stage 1 — is this a persistent industrial source?"
            subtitle={`Frozen M2 baseline · ${n(conf.population)} places · ${n(conf.positives)} verified industrial`}
            right={
              <div class="flex gap-1">
                {["0.5", "0.9"].map((t) => (
                  <button key={t} onClick={() => setThreshold(t)}
                          class="h-[26px] px-2.5 rounded-full text-[11px] font-semibold border cursor-pointer"
                          style={threshold === t
                            ? "background:#0f17201a;border-color:#0f172040;color:#0f1720"
                            : "background:#fff;border-color:#e3e6ea;color:#64748b"}>
                    threshold {t}
                  </button>
                ))}
              </div>
            }
          >
            <div class="p-4">
              <BinaryMatrix m={conf.full_population?.[threshold]} />
              <p class="text-[12px] text-muted m-0 mt-4 leading-[18px]">
                {threshold === "0.5"
                  ? "At 0.5 the model finds more real sources while staying accurate — the better setting for finding sites worth investigating."
                  : "At 0.9 almost everything it flags is real, but it misses most sources. The cost of certainty is recall."}
              </p>
            </div>
          </Panel>

          <Panel
            title="Stage 1 on field-verified cells only"
            subtitle={`${n(conf.verified_subset?.n)} cells a person checked · threshold ${threshold}`}
          >
            <div class="p-4">
              <BinaryMatrix m={conf.verified_subset?.[threshold]} />
            </div>
          </Panel>

          <Panel
            title="Stage 2b — which industry is it?"
            subtitle="Out-of-fold across held-out 20° regions. Green diagonal is correct; red is confusion."
          >
            <div class="p-4">
              <MultiMatrix labels={s2.confusion_matrix?.labels} rows={s2.confusion_matrix?.rows_are_truth || []} />
              <div class="mt-4 rounded-[8px] bg-wash border border-rule p-3">
                <p class="m-0 text-[12px] font-semibold">Why this matrix is mostly red</p>
                <p class="m-0 mt-1 text-[12px] text-muted leading-[18px]">
                  From orbit a power station, a smelter and a quarry all look like
                  steady night-time heat. The errors run both ways in near-equal
                  numbers — power→factory and factory→power — which means the classes
                  are indistinguishable in thermal data, not that the model is biased.
                  Telling them apart needs satellite imagery. Until then a specific
                  type is only published when the model is at least 90% confident.
                </p>
              </div>
            </div>
          </Panel>
        </div>

        <div class="flex flex-col gap-4">
          <Panel title="Stage 2b accuracy by industry" subtitle="F1 out of 1.00">
            <div class="p-4"><ScoreBars rows={perClass} threshold={0.5} /></div>
          </Panel>

          <Panel title="DBSCAN spatial validation"
                 subtitle={`eps ${db.parameters?.eps_km ?? "—"} km · min_samples ${db.parameters?.min_samples ?? "—"}`}>
            <div class="p-4">
              <div class="grid gap-3" style="grid-template-columns:repeat(3,1fr)">
                {[["Clusters", n(db.clusters)], ["Noise", `${db.noise_pct ?? "—"}%`],
                  ["Silhouette", db.silhouette?.toFixed(3) ?? "—"]].map(([k, v]) => (
                  <div key={k}>
                    <span class="label-caps">{k}</span>
                    <div class="text-[18px] font-semibold tabular-nums">{v}</div>
                  </div>
                ))}
              </div>
              <p class="label-caps m-0 mt-4 mb-2">What confirmed clusters sit on</p>
              <BarChart data={industries} valueKey="count" labelKey="label" maxRows={8} />
              <p class="text-[11px] text-muted m-0 mt-3 leading-[16px]">
                High noise is expected: most industrial sources are one isolated cell,
                so DBSCAN finds industrial complexes rather than single sites.
              </p>
            </div>
          </Panel>

          <Panel title="Calibration">
            <div class="p-4 grid gap-3" style="grid-template-columns:1fr 1fr">
              <div><span class="label-caps">Brier score</span>
                <div class="text-[13px] tabular-nums mt-0.5">
                  {cal.brier_raw?.toFixed(4)} → <b>{cal.brier_calibrated?.toFixed(4)}</b>
                </div></div>
              <div><span class="label-caps">Worst reliability gap</span>
                <div class="text-[13px] tabular-nums mt-0.5">
                  {cal.max_gap_raw?.toFixed(3)} → <b>{cal.max_gap_calibrated?.toFixed(3)}</b>
                </div></div>
              <p class="text-[11px] text-muted m-0 col-span-2 leading-[16px]">
                Isotonic calibration, kept separate from the accuracy numbers above —
                it fixes what a score means without changing how well it ranks.
              </p>
            </div>
          </Panel>

          <Panel title="Independence guarantees">
            <div class="max-h-[300px] overflow-y-auto">
              {(m2.independence_guarantees || []).map((g, i) => (
                <div key={i} class="flex gap-2 px-4 py-2.5 border-b border-[#f1f5f9]">
                  <Icon name="check_circle" style="font-size:15px;color:#0f8a3d;flex:none;margin-top:1px" />
                  <span class="text-[12px] leading-[17px]">{g}</span>
                </div>
              ))}
            </div>
          </Panel>

          {m2.known_limitations?.length > 0 && (
            <Panel title="Known limitations">
              <div class="p-4 flex flex-col gap-2">
                {m2.known_limitations.map((l, i) => (
                  <p key={i} class="m-0 text-[12px] text-muted leading-[17px]">• {l}</p>
                ))}
              </div>
            </Panel>
          )}
        </div>
      </div>
    </>
  );
}
