import { useEffect, useState } from "preact/hooks";
import { Icon } from "./ui.jsx";

/* ---------------------------------------------------------------------------
   Hash router. Pages are addressable (#/investigation/32085930), so a link to
   one source can be shared, bookmarked, or opened from a map popup - which a
   component-state router cannot do. No dependency needed for this much.
--------------------------------------------------------------------------- */
export function parseHash() {
  const [page = "dashboard", ...rest] = (location.hash.replace(/^#\/?/, "") || "dashboard").split("/");
  return { page, param: rest.join("/") || null };
}

export function useRoute() {
  const [route, setRoute] = useState(parseHash);
  useEffect(() => {
    const on = () => { setRoute(parseHash()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const go = (path) => { location.hash = `#/${path}`; };

/* ---------------------------------------------------------------------------
   Page furniture.
--------------------------------------------------------------------------- */
export function PageHeader({ eyebrow, title, sub, right }) {
  return (
    <header class="mb-2">
      {eyebrow && <span class="page-eyebrow"><span class="w-2 h-2 bg-[var(--color-accent)]" />{eyebrow}</span>}
      <div class="flex items-end justify-between gap-4 flex-wrap">
        <h1 class="page-title">{title}</h1>
        {right}
      </div>
      {sub && <p class="page-sub">{sub}</p>}
      <div class="border-b-2 border-rule mt-5" />
    </header>
  );
}

export function Section({ idx, title, note, children }) {
  return (
    <section>
      <div class="section-head">
        {idx && <span class="idx">{idx}</span>}
        <h2>{title}</h2>
        {note && <span class="note">{note}</span>}
      </div>
      {children}
    </section>
  );
}

/** KPI tile: label, icon, one big mono number. */
export function Kpi({ label, value, icon, tone, sub }) {
  return (
    <div class="panel-flat px-4 py-3.5 flex flex-col gap-2 min-h-[92px]">
      <span class="label-caps">{label}</span>
      <div class="flex items-center gap-2.5">
        {icon && <Icon name={icon} style={`font-size:20px;color:${tone || "var(--color-ink)"}`} />}
        <span class="kpi-value" style={tone ? `color:${tone}` : ""}>{value ?? "…"}</span>
      </div>
      {sub && <span class="text-[12px] text-muted font-semibold">{sub}</span>}
    </div>
  );
}

/** Bordered tab chips; the active one fills black. */
export function Tabs({ options, value, onChange }) {
  return (
    <div class="flex flex-wrap gap-2">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button key={String(o.value)} onClick={() => onChange(o.value)}
                  class="h-8 px-3 border-2 border-rule text-[11px] font-extrabold tracking-[0.06em] uppercase cursor-pointer"
                  style={on ? "background:var(--color-bar);color:#fff;border-color:var(--color-bar)"
                            : "background:var(--color-panel);color:var(--color-ink)"}>
            {o.label}{o.count != null && <span class="mono ml-1.5 opacity-80">({o.count.toLocaleString()})</span>}
          </button>
        );
      })}
    </div>
  );
}

/** Pager with a rows-per-page selector. */
export function Pager({ offset, limit, total, onOffset, onLimit }) {
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  const from = total ? offset + 1 : 0;
  const to = Math.min(offset + limit, total);
  return (
    <div class="flex items-center justify-between gap-3 flex-wrap px-4 py-3 border-t-2 border-rule">
      <button class="btn h-8" disabled={page <= 1} onClick={() => onOffset(Math.max(0, offset - limit))}>Previous</button>
      <span class="mono text-[12px]">Page {page} of {pages} ({from.toLocaleString()}–{to.toLocaleString()} of {total.toLocaleString()})</span>
      <div class="flex items-center gap-2">
        {onLimit && (
          <select class="field h-8" value={limit} onChange={(e) => onLimit(Number(e.target.value))}>
            {[10, 25, 50, 100].map((n) => <option key={n} value={n}>{n} rows</option>)}
          </select>
        )}
        <button class="btn h-8" disabled={page >= pages} onClick={() => onOffset(offset + limit)}>Next</button>
      </div>
    </div>
  );
}

/** Save rows as CSV or JSON. Works in the local app; generated client-side. */
export function download(name, rows, kind = "csv") {
  let body, type;
  if (kind === "json") {
    body = JSON.stringify(rows, null, 2); type = "application/json";
  } else {
    const cols = rows.length ? Object.keys(rows[0]) : [];
    const esc = (v) => {
      const s = v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    body = [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
    type = "text/csv";
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([body], { type }));
  a.download = `${name}.${kind}`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
