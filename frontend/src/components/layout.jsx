import { useEffect, useState } from "preact/hooks";
import { Icon } from "./ui.jsx";

/* ---------------------------------------------------------------------------
   Hash router. Every page and source is addressable (#/investigation/123),
   so a link to one source can be shared or bookmarked.
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
      {eyebrow && <span class="page-eyebrow"><span class="w-4 h-[3px] rounded-full ironbow-edge" />{eyebrow}</span>}
      <div class="flex items-end justify-between gap-4 flex-wrap">
        <h1 class="page-title">{title}</h1>
        {right}
      </div>
      {sub && <p class="page-sub">{sub}</p>}
    </header>
  );
}

/** Section: a quiet title with an optional note on the right. */
export function Section({ title, note, children }) {
  return (
    <section>
      <div class="section-head">
        <h2>{title}</h2>
        {note && <span class="note">{note}</span>}
      </div>
      {children}
    </section>
  );
}

/** KPI card: tinted icon badge, label, large figure. */
export function Kpi({ label, value, icon, tone, sub }) {
  const c = tone || "var(--color-accent)";
  return (
    <div class="panel px-4 py-4 flex items-start gap-3.5 min-h-[96px]">
      {icon && (
        <span class="w-10 h-10 shrink-0 rounded-[10px] flex items-center justify-center"
              style={`background:color-mix(in srgb, ${c} 13%, transparent);color:${c}`}>
          <Icon name={icon} style="font-size:21px" />
        </span>
      )}
      <div class="min-w-0">
        <span class="label-caps">{label}</span>
        <div class="kpi-value mt-1.5" style={tone ? `color:${tone}` : ""}>{value ?? "…"}</div>
        {sub && <span class="block mt-1 text-[12px] text-muted">{sub}</span>}
      </div>
    </div>
  );
}

/** Segmented control. */
export function Tabs({ options, value, onChange }) {
  return (
    <div class="inline-flex flex-wrap gap-1 p-1 rounded-[10px] bg-[var(--color-wash)] border border-rule">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button key={String(o.value)} onClick={() => onChange(o.value)}
                  class="h-8 px-3 rounded-[7px] border-0 text-[13px] font-semibold cursor-pointer transition-colors"
                  style={on ? "background:var(--color-panel);color:var(--color-ink);box-shadow:0 1px 3px rgb(0 0 0 / .12)"
                            : "background:transparent;color:var(--color-muted)"}>
            {o.label}{o.count != null && <span class="mono ml-1.5 text-[11px]" style="color:var(--color-muted)">{o.count.toLocaleString()}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function Pager({ offset, limit, total, onOffset, onLimit }) {
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  const from = total ? offset + 1 : 0;
  const to = Math.min(offset + limit, total);
  return (
    <div class="flex items-center justify-between gap-3 flex-wrap px-4 py-3 border-t border-rule">
      <span class="text-[13px] text-muted">
        <span class="mono text-[var(--color-ink)]">{from.toLocaleString()}–{to.toLocaleString()}</span> of <span class="mono">{total.toLocaleString()}</span>
      </span>
      <div class="flex items-center gap-2">
        {onLimit && (
          <select class="field h-8" value={limit} onChange={(e) => onLimit(Number(e.target.value))}>
            {[10, 25, 50, 100].map((n) => <option key={n} value={n}>{n} per page</option>)}
          </select>
        )}
        <button class="btn h-8 w-8 px-0" aria-label="Previous page" disabled={page <= 1} onClick={() => onOffset(Math.max(0, offset - limit))}>
          <Icon name="chevron_left" />
        </button>
        <span class="mono text-[12px] text-muted">{page} / {pages}</span>
        <button class="btn h-8 w-8 px-0" aria-label="Next page" disabled={page >= pages} onClick={() => onOffset(offset + limit)}>
          <Icon name="chevron_right" />
        </button>
      </div>
    </div>
  );
}

/** Save rows as CSV or JSON, generated in the browser. */
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
