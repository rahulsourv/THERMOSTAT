import { useEffect, useState } from "preact/hooks";
import { api } from "../api.js";
import { Icon } from "./ui.jsx";
import { go } from "./layout.jsx";

export const NAV = [
  { group: "Monitor", items: [
    { id: "dashboard", label: "Overview", icon: "space_dashboard" },
    { id: "alerts", label: "Alerts", icon: "notifications" },
    { id: "anomaly", label: "Change & anomaly", icon: "trending_up" },
    { id: "fires", label: "Active fires", icon: "local_fire_department" },
  ] },
  { group: "Investigate", items: [
    { id: "search", label: "Search", icon: "search" },
    { id: "investigation", label: "Source detail", icon: "frame_inspect" },
    { id: "assessment", label: "Event assessment", icon: "fact_check" },
    { id: "classification", label: "Classification", icon: "category" },
  ] },
  { group: "Reference", items: [
    { id: "reports", label: "Reports", icon: "description" },
    { id: "layers", label: "Data layers", icon: "layers" },
    { id: "system", label: "System & model", icon: "tune" },
  ] },
];
const LABEL = Object.fromEntries(NAV.flatMap((g) => g.items.map((i) => [i.id, i.label])));

// A successful run older than this is shown as stale. The job fires daily at
// 05:00 IST; 26 hours leaves slack for a late start without letting a dead
// scheduler hide behind a green light.
const STALE_AFTER_HOURS = 26;

function PipelineChip() {
  const [runs, setRuns] = useState(null);
  useEffect(() => { api.runs(1).then(setRuns).catch(() => setRuns({ error: true })); }, []);

  let tone = "var(--color-muted)", label = "Checking pipeline", title = "";
  if (runs?.error || (runs && !runs.runs?.length)) {
    tone = "var(--color-high)"; label = "Pipeline unknown";
  } else if (runs) {
    const last = runs.runs[0];
    const ok = last.status === "success";
    const hours = (Date.now() - new Date(last.started_at).getTime()) / 36e5;
    const age = hours < 1 ? "just now" : hours < 48 ? `${Math.round(hours)}h ago` : `${Math.round(hours / 24)}d ago`;
    tone = !ok ? "var(--color-high)" : hours > STALE_AFTER_HOURS ? "var(--color-medium)" : "var(--color-confirmed)";
    label = !ok ? "Pipeline failed" : hours > STALE_AFTER_HOURS ? `Data stale · ${age}` : `Updated ${age}`;
    title = `Last run ${new Date(last.started_at).toLocaleString()} · ${last.status} · ${last.detections?.toLocaleString() ?? "—"} detections`;
  }
  return (
    <span title={title} class="hidden sm:inline-flex items-center gap-2 h-8 px-3 rounded-full border border-rule bg-[var(--color-panel)] text-[12px] font-semibold">
      <span class="relative flex w-2 h-2">
        <span class="absolute inset-0 rounded-full animate-ping opacity-40" style={`background:${tone}`} />
        <span class="relative w-2 h-2 rounded-full" style={`background:${tone}`} />
      </span>
      {label}
    </span>
  );
}

function ThemeToggle() {
  const [dark, setDark] = useState(() => document.documentElement.getAttribute("data-theme") === "dark");
  const flip = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.setAttribute("data-theme", next ? "dark" : "light");
    try { localStorage.setItem("thermostats-theme", next ? "dark" : "light"); } catch (e) { /* storage blocked */ }
  };
  return (
    <button onClick={flip} aria-label="Toggle theme" class="btn h-8 w-8 px-0 rounded-full">
      <Icon name={dark ? "light_mode" : "dark_mode"} style="font-size:17px" />
    </button>
  );
}

/** Mark: an aperture ringed in the ironbow ramp. */
function Mark() {
  return (
    <span class="w-9 h-9 rounded-[10px] p-[2px]" style="background:conic-gradient(from 200deg,#2b0a3d,#7a1f76,#d6337a,#f26b1d,#ffc93c,#2b0a3d)">
      <span class="w-full h-full rounded-[8px] bg-[#17141f] flex items-center justify-center">
        <span class="w-3 h-3 rounded-full bg-[#ff6a1a] shadow-[0_0_10px_#ff6a1a]" />
      </span>
    </span>
  );
}

export function Shell({ route, children }) {
  const [open, setOpen] = useState(() => window.innerWidth >= 1024);
  const pick = (id) => { go(id); if (window.innerWidth < 1024) setOpen(false); };

  return (
    <div class="min-h-screen flex">
      {open && (
        <aside class="fixed lg:sticky top-0 z-[1000] h-screen w-[240px] shrink-0 flex flex-col bg-[var(--color-bar)] text-[#d8d4e4]">
          <div class="h-[3px] ironbow-edge" />
          <button onClick={() => pick("dashboard")} class="flex items-center gap-3 px-5 pt-5 pb-6 bg-transparent border-0 cursor-pointer text-left">
            <Mark />
            <span>
              <span class="block text-[17px] font-bold text-white tracking-[-0.01em]" style="font-family:var(--font-display)">ThermoStats</span>
              <span class="block text-[11px] text-[#8f89a3]">Thermal source intelligence</span>
            </span>
          </button>
          <nav class="flex-1 overflow-y-auto px-3 pb-4">
            {NAV.map((g) => (
              <div key={g.group} class="mb-5">
                <p class="m-0 mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#6f6985]">{g.group}</p>
                {g.items.map((it) => {
                  const on = it.id === route.page;
                  return (
                    <button key={it.id} onClick={() => pick(it.id)}
                            class="relative w-full flex items-center gap-3 px-3 py-2 mb-0.5 rounded-[8px] border-0 text-left text-[13.5px] font-medium cursor-pointer transition-colors"
                            style={on ? "background:rgb(255 106 26 / .14);color:#fff" : "background:transparent;color:#bdb7cc"}>
                      {on && <span class="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-[#ff6a1a]" />}
                      <Icon name={it.icon} style={`font-size:19px;color:${on ? "#ff8a4c" : "#8f89a3"}`} />{it.label}
                    </button>
                  );
                })}
              </div>
            ))}
          </nav>
          <div class="px-5 py-4 border-t border-[#2a2636] text-[11px] text-[#6f6985] leading-[16px]">
            NASA FIRMS · VIIRS NOAA-20<br />SIH26162
          </div>
        </aside>
      )}

      <div class="flex-1 min-w-0 flex flex-col">
        <header class="sticky top-0 z-[900] h-14 px-4 lg:px-8 flex items-center gap-3 bg-[color-mix(in_srgb,var(--color-canvas)_85%,transparent)] backdrop-blur-md border-b border-rule">
          <button onClick={() => setOpen(!open)} aria-label={open ? "Close navigation" : "Open navigation"} class="btn h-8 w-8 px-0">
            <Icon name={open ? "left_panel_close" : "menu"} style="font-size:19px" />
          </button>
          <span class="text-[13px] text-muted hidden md:inline">ThermoStats <span class="mx-1.5">/</span><b class="text-[var(--color-ink)] font-semibold">{LABEL[route.page] || "Overview"}</b></span>
          <div class="ml-auto flex items-center gap-2">
            <PipelineChip />
            <button onClick={() => location.reload()} class="btn h-8" aria-label="Refresh data">
              <Icon name="refresh" style="font-size:17px" /><span class="hidden sm:inline">Refresh</span>
            </button>
            <ThemeToggle />
          </div>
        </header>
        <main class="flex-1 px-4 lg:px-8 py-7">
          <div class="max-w-[1360px] mx-auto">{children}</div>
          <footer class="max-w-[1360px] mx-auto mt-14 pt-5 border-t border-rule flex justify-between gap-4 flex-wrap text-[12px] text-muted">
            <span>ThermoStats · built for SIH26162</span>
            <span>Data: NASA FIRMS, OpenStreetMap, WRI, Smithsonian GVP, IHS v3.0</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

export function ErrorScreen({ message }) {
  return (
    <div class="panel p-8 text-center max-w-[560px] mx-auto mt-16">
      <Icon name="cloud_off" style="font-size:32px;color:var(--color-high)" />
      <h2 class="text-[20px] font-semibold mt-3 mb-1" style="font-family:var(--font-display)">Cannot reach the API</h2>
      <p class="text-[13px] text-muted mb-4">{message}</p>
      <code class="mono block text-[12px] bg-[var(--color-wash)] border border-rule rounded-[8px] p-3 text-left">
        ML\.venv\Scripts\python.exe -m uvicorn backend.app:app --port 8000
      </code>
    </div>
  );
}
