/** Shared primitives for the ThermoStats Scientific design system. */

import {
  CLASS_BY_ID as CLASS_INFO,
  CLASS_SOURCES as SOURCE_INFO,
  gmapsUrl,
  gmapsSatelliteUrl,
} from "../api.js";

/**
 * Open this exact coordinate in Google Maps.
 *
 * stopPropagation matters: these links sit inside rows that are themselves
 * clickable (selecting the place). Without it, opening the map would also
 * change the selection behind the new tab.
 */
export function MapLink({ lat, lon, satellite = false, compact = false }) {
  if (lat == null || lon == null) return null;
  const href = satellite ? gmapsSatelliteUrl(lat, lon) : gmapsUrl(lat, lon);
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(e) => e.stopPropagation()}
      title={`Open ${lat.toFixed(4)}, ${lon.toFixed(4)} in Google Maps`}
      class={
        compact
          ? "inline-flex items-center gap-1 text-[11px] font-semibold text-[#2563eb] hover:underline"
          : "btn h-7 text-[11px]"
      }
    >
      <Icon name={satellite ? "satellite_alt" : "pin_drop"}
            style="font-size:14px" />
      {compact ? "Google Maps" : (satellite ? "Satellite view" : "Google Maps")}
    </a>
  );
}

export const n = (v, d = 0) =>
  v === null || v === undefined || Number.isNaN(Number(v))
    ? "—"
    : Number(v).toLocaleString(undefined, {
        minimumFractionDigits: d,
        maximumFractionDigits: d,
      });

export const pct = (v, d = 0) =>
  v === null || v === undefined ? "—" : `${(Number(v) * 100).toFixed(d)}%`;

export const SEMANTIC = {
  High: "#dc2626",
  Medium: "#f59e0b",
  Low: "#2563eb",
  "Natural (volcano)": "#7c3aed",
  confirmed: "#16a34a",
  muted: "#64748b",
  Large: "#b91c1c",
  Moderate: "#ea580c",
  Small: "#eab308",
};

export function Icon({ name, className = "", style = "" }) {
  return (
    <span class={`material-symbols-outlined ${className}`} style={style}>
      {name}
    </span>
  );
}

/**
 * Status pill. Tinted ground at ~10% of the semantic hue, hairline border
 * at ~25%, text at full strength — per the design system.
 */
export function Pill({ tone = "#64748b", dot = false, children }) {
  return (
    <span
      class="pill"
      style={`background:${tone}1a; border-color:${tone}40; color:${tone}`}
    >
      {dot && <span class="pill-dot" style={`background:${tone}`} />}
      {children}
    </span>
  );
}

/**
 * The event type of a thermal source, with how it was decided.
 *
 * The provenance dot is not decoration. A type from OpenStreetMap is a
 * mapped fact; a type from the classifier is a prediction about somewhere
 * nobody has surveyed. Showing them identically would overstate the second,
 * so every badge carries its source.
 */
export function ClassBadge({ eventClass, source, confidence, showSource = true }) {
  const info = CLASS_INFO[eventClass] || CLASS_INFO.unclassified;
  const provenance = SOURCE_INFO[source] || SOURCE_INFO.none;

  return (
    <span class="inline-flex items-center gap-1.5">
      <span
        class="pill"
        style={`background:${info.tone}1a; border-color:${info.tone}40; color:${info.tone}`}
        title={info.label}
      >
        <span class="pill-dot" style={`background:${info.tone}`} />
        {info.label}
      </span>
      {showSource && (
        <span
          class="text-[10px] font-semibold uppercase tracking-[0.06em]"
          style={`color:${provenance.tone}`}
          title={provenance.hint}
        >
          {provenance.label}
          {confidence != null && source === "predicted"
            ? ` ${(confidence * 100).toFixed(0)}%`
            : ""}
        </span>
      )}
    </span>
  );
}

/** Big metric tile with a semantic left edge. */
export function StatTile({ label, value, sub, tone, icon, dot = true }) {
  return (
    <div
      class="panel px-4 py-3 flex flex-col justify-between min-h-[104px]"
      style={tone ? `border-left:4px solid ${tone}` : ""}
    >
      <div class="flex items-start justify-between gap-2">
        <span class="label-caps leading-[14px]">{label}</span>
        {icon && (
          <Icon
            name={icon}
            style={`font-size:17px;color:${tone || "#94a3b8"}`}
          />
        )}
      </div>
      <div
        class="text-[32px] font-semibold tracking-[-0.02em] leading-[38px] mt-1"
        style={tone ? `color:${tone}` : ""}
      >
        {value}
      </div>
      {sub && (
        <div class="flex items-center gap-1.5 text-[12px] text-muted">
          {dot && (
            <span
              class="pill-dot"
              style={`background:${tone || "#94a3b8"}`}
            />
          )}
          {sub}
        </div>
      )}
    </div>
  );
}

export function Panel({ title, subtitle, right, children, pad = false, className = "" }) {
  return (
    <div class={`panel flex flex-col ${className}`}>
      {(title || right) && (
        <div class="flex items-start justify-between gap-3 px-4 py-3 border-b border-rule flex-wrap">
          <div>
            {title && (
              <h2 class="text-[15px] font-semibold tracking-[-0.005em] m-0">
                {title}
              </h2>
            )}
            {subtitle && (
              <p class="text-[12px] text-muted m-0 mt-0.5">{subtitle}</p>
            )}
          </div>
          {right && <div class="flex items-center gap-2">{right}</div>}
        </div>
      )}
      <div class={pad ? "p-4" : ""}>{children}</div>
    </div>
  );
}

/** Horizontal contribution/score bar. */
export function Bar({ value, max = 1, tone = "#2563eb", height = 6 }) {
  const width = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div
      class="w-full rounded-full bg-[#eef1f6] overflow-hidden"
      style={`height:${height}px`}
    >
      <div
        class="h-full rounded-full"
        style={`width:${width}%;background:${tone}`}
      />
    </div>
  );
}

export function Empty({ icon = "center_focus_weak", title, body }) {
  return (
    <div class="border border-dashed border-edge rounded-[10px] m-4 py-12 px-6 text-center">
      <Icon
        name={icon}
        style="font-size:26px;color:#94a3b8"
      />
      <p class="text-[15px] font-semibold mt-2 mb-1">{title}</p>
      {body && <p class="text-[12px] text-muted m-0 max-w-[380px] mx-auto">{body}</p>}
    </div>
  );
}

export function Loading({ label = "Loading" }) {
  return (
    <div class="py-12 text-center text-muted text-[12px]">{label}…</div>
  );
}

/** Segmented filter control. */
export function Segmented({ options, value, onChange }) {
  return (
    <div class="flex items-center gap-1 flex-wrap">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={String(o.value)}
            onClick={() => onChange(o.value)}
            class="h-[26px] px-2.5 rounded-full text-[11px] font-semibold tracking-[0.04em] uppercase border cursor-pointer transition-colors"
            style={
              active
                ? `background:${o.tone || "#0f172a"}1a;border-color:${o.tone || "#0f172a"}40;color:${o.tone || "#0f172a"}`
                : "background:#fff;border-color:#e3e6ea;color:#64748b"
            }
          >
            {o.tone && (
              <span
                class="pill-dot inline-block mr-1.5 align-middle"
                style={`background:${o.tone}`}
              />
            )}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** Toggle switch, 28x16 per the design system. */
export function Toggle({ checked, onChange, label }) {
  return (
    <label class="flex items-center gap-2 cursor-pointer select-none">
      <span class="text-[12px] text-muted">{label}</span>
      <span
        onClick={() => onChange(!checked)}
        class="relative inline-block w-7 h-4 rounded-full transition-colors"
        style={`background:${checked ? "#2563eb" : "#cbd5e1"}`}
      >
        <span
          class="absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all"
          style={`left:${checked ? "14px" : "2px"}`}
        />
      </span>
    </label>
  );
}
