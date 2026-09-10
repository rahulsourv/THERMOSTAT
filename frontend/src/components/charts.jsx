/**
 * Chart primitives for ThermoStats.
 *
 * Two rules drive every choice here, and they are not stylistic:
 *
 * 1. Colour is assigned by the JOB, not by the category. The class-breakdown
 *    chart compares magnitudes, so it uses ONE hue light-to-dark and lets the
 *    row label carry identity. Giving nine thermal classes nine hues failed
 *    colour-blindness validation outright - agriculture green and wildfire
 *    green were 5.7 apart on a 15 floor, indistinguishable even with full
 *    colour vision.
 *
 * 2. Anything where colour does carry identity is capped and validated. The
 *    evidence-mix bar uses four hues from a palette checked for CVD
 *    separation, and every segment is also directly labelled, so colour is
 *    never the only channel.
 */

import { useState } from "preact/hooks";

// Single-hue sequential ramp: more is darker. Used wherever the job is
// "compare magnitude", which is most of this dashboard.
export const SEQ = [
  "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5",
  "#2a78d6", "#256abf", "#1c5cab", "#184f95",
];

// Validated categorical slots, only for the few places identity is the job.
export const CAT = {
  mapped: "#1baf7a",
  predicted: "#2a78d6",
  rule: "#eda100",
  none: "#94a3b8",
};

export const fmt = (v) =>
  v === null || v === undefined ? "—" : Number(v).toLocaleString();

/** Ramp step for a value's share of the maximum. */
function step(value, max) {
  if (!max) return SEQ[3];
  const t = Math.sqrt(value / max);          // sqrt so small bars stay visible
  return SEQ[Math.min(SEQ.length - 1, Math.max(2, Math.round(t * 7)))];
}

/**
 * Horizontal bar chart. Horizontal because the category names are long
 * ("Agricultural burning") and vertical columns would rotate them.
 */
export function BarChart({ data, valueKey = "value", labelKey = "label",
                           unit = "", onSelect, selected, maxRows = 12 }) {
  const [hover, setHover] = useState(null);
  const rows = data.slice(0, maxRows);
  const max = Math.max(...rows.map((r) => r[valueKey]), 1);
  const total = data.reduce((sum, r) => sum + r[valueKey], 0) || 1;

  return (
    <div class="flex flex-col gap-1.5">
      {rows.map((row) => {
        const value = row[valueKey];
        const pct = value / max;
        const isOn = selected === row.id;
        return (
          <div
            key={row.id ?? row[labelKey]}
            onClick={() => onSelect && onSelect(isOn ? null : row.id)}
            onMouseEnter={() => setHover(row.id)}
            onMouseLeave={() => setHover(null)}
            class={`group ${onSelect ? "cursor-pointer" : ""}`}
            title={`${row[labelKey]}: ${fmt(value)} ${unit}`}
          >
            <div class="flex items-baseline justify-between gap-2 mb-0.5">
              <span class={`text-[12px] ${isOn ? "font-semibold text-ink" : "text-ink"}`}>
                {row.icon && (
                  <span class="material-symbols-outlined align-middle mr-1"
                        style={`font-size:14px;color:${row.tone || "#64748b"}`}>
                    {row.icon}
                  </span>
                )}
                {row[labelKey]}
              </span>
              <span class="text-[12px] tabular-nums text-muted">
                <b class="text-ink">{fmt(value)}</b>
                <span class="ml-1.5 text-[11px]">
                  {((value / total) * 100).toFixed(1)}%
                </span>
              </span>
            </div>
            <div class="h-[10px] rounded-[3px] bg-[#eef1f6] overflow-hidden">
              <div
                class="h-full rounded-[3px] transition-[width,opacity] duration-200"
                style={`width:${Math.max(pct * 100, 1.5)}%;
                        background:${step(value, max)};
                        opacity:${hover && hover !== row.id ? 0.55 : 1}`}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * One stacked bar showing how a whole splits by evidence quality.
 *
 * A 2px surface-coloured gap sits between segments so adjacent fills never
 * touch - without it two similar hues read as one block.
 */
export function StackedBar({ segments, height = 22 }) {
  const total = segments.reduce((sum, s) => sum + s.value, 0) || 1;
  return (
    <div>
      <div class="flex rounded-[5px] overflow-hidden" style={`height:${height}px`}>
        {segments.filter((s) => s.value > 0).map((s, i) => (
          <div
            key={s.label}
            class="flex items-center justify-center"
            style={`width:${(s.value / total) * 100}%;background:${s.tone};
                    ${i ? "margin-left:2px" : ""}`}
            title={`${s.label}: ${fmt(s.value)} (${((s.value / total) * 100).toFixed(1)}%)`}
          >
            {s.value / total > 0.08 && (
              <span class="text-[10px] font-bold text-white drop-shadow">
                {((s.value / total) * 100).toFixed(0)}%
              </span>
            )}
          </div>
        ))}
      </div>
      <div class="flex flex-wrap gap-x-3 gap-y-1 mt-2">
        {segments.filter((s) => s.value > 0).map((s) => (
          <span key={s.label} class="flex items-center gap-1.5 text-[11px] text-muted">
            <span class="w-2.5 h-2.5 rounded-[2px]" style={`background:${s.tone}`} />
            {s.label}
            <b class="text-ink tabular-nums">{fmt(s.value)}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * Per-class accuracy. Deliberately a bar chart against a visible 1.0 axis,
 * not a table of decimals: the point a reader must take away is how FAR
 * SHORT these bars fall, and a column of "0.32" does not communicate that.
 */
export function ScoreBars({ rows, threshold = 0.5 }) {
  return (
    <div class="flex flex-col gap-2">
      {rows.map((r) => {
        const good = r.value >= threshold;
        return (
          <div key={r.label}>
            <div class="flex items-baseline justify-between gap-2 mb-0.5">
              <span class="text-[12px]">{r.label}</span>
              <span class={`text-[12px] font-semibold tabular-nums ${good ? "" : "text-muted"}`}
                    style={good ? "color:#0ca30c" : ""}>
                {r.value.toFixed(2)}
                {r.support != null && (
                  <span class="ml-1.5 text-[11px] font-normal text-muted">
                    n={fmt(r.support)}
                  </span>
                )}
              </span>
            </div>
            <div class="relative h-[9px] rounded-[3px] bg-[#eef1f6] overflow-hidden">
              <div class="h-full rounded-[3px]"
                   style={`width:${r.value * 100}%;background:${good ? "#0ca30c" : "#94a3b8"}`} />
              {/* The bar people should be clearing, drawn so it cannot be missed */}
              <div class="absolute top-0 bottom-0 w-px bg-[#0f172a] opacity-40"
                   style={`left:${threshold * 100}%`} />
            </div>
          </div>
        );
      })}
      <p class="text-[11px] text-muted m-0 mt-1">
        Bars are F1 out of a possible 1.00. The vertical line marks{" "}
        {threshold.toFixed(2)} — below it the model is wrong more often than right.
      </p>
    </div>
  );
}

/**
 * Confidence histogram with the publish gate drawn on it. This exists to
 * show WHY most places are reported as "type unspecified" rather than
 * leaving that decision looking arbitrary.
 */
export function ConfidenceHistogram({ bins, gate = 0.9 }) {
  const max = Math.max(...bins.map((b) => b.count), 1);
  return (
    <div>
      <div class="flex items-end gap-1 h-[110px]">
        {bins.map((b) => {
          const published = b.from >= gate;
          return (
            <div key={b.from} class="flex-1 flex flex-col items-center justify-end h-full"
                 title={`${(b.from * 100).toFixed(0)}–${(b.to * 100).toFixed(0)}% confident: ${fmt(b.count)} places`}>
              <span class="text-[9px] text-muted mb-0.5 tabular-nums">
                {b.count ? fmt(b.count) : ""}
              </span>
              <div
                class="w-full rounded-t-[3px]"
                style={`height:${Math.max((b.count / max) * 100, b.count ? 2 : 0)}%;
                        background:${published ? "#0ca30c" : "#c7d2e0"}`}
              />
            </div>
          );
        })}
      </div>
      <div class="flex gap-1 mt-1">
        {bins.map((b) => (
          <span key={b.from} class="flex-1 text-center text-[9px] text-muted tabular-nums">
            {(b.from * 100).toFixed(0)}
          </span>
        ))}
      </div>
      <p class="text-[11px] text-muted m-0 mt-2">
        Model confidence, %. Only the green bars ({(gate * 100).toFixed(0)}%+) get a
        named industry type — below that the prediction is wrong more often than
        right, so the place is reported as “industrial, type unspecified”.
      </p>
    </div>
  );
}
