import { useEffect, useState } from "preact/hooks";
import { api } from "../api.js";
import { Icon } from "./ui.jsx";
import { go } from "./layout.jsx";

export const NAV = [
  { group: "General", items: [
    { id: "dashboard", label: "Dashboard", icon: "dashboard" },
    { id: "search", label: "Search & Discovery", icon: "search" },
    { id: "investigation", label: "Source Investigation", icon: "plagiarism" },
    { id: "assessment", label: "Event Assessment", icon: "fact_check" },
    { id: "anomaly", label: "Change & Anomaly", icon: "trending_up" },
    { id: "alerts", label: "Alerts", icon: "notifications" },
    { id: "fires", label: "Active Fires", icon: "local_fire_department" },
  ] },
  { group: "Reporting", items: [
    { id: "classification", label: "Classification", icon: "category" },
    { id: "reports", label: "Intelligence Reports", icon: "description" },
    { id: "layers", label: "Data Layers", icon: "layers" },
  ] },
  { group: "System", items: [
    { id: "system", label: "System / Model", icon: "settings" },
  ] },
];

// A run older than this is shown as stale. The job fires daily at 05:00 IST;
// 26 hours leaves slack for a late start without letting a dead scheduler
// hide behind a green badge - which is exactly how a 07:00 IST misconfiguration
// once went unnoticed while the dashboard looked perfectly healthy.
const STALE_AFTER_HOURS = 26;

function PipelineChip() {
  const [runs, setRuns] = useState(null);
  useEffect(() => { api.runs(1).then(setRuns).catch(() => setRuns({ error: true })); }, []);

  let tone = "#a1a1aa", label = "Checking pipeline", title = "";
  if (runs?.error || (runs && !runs.runs?.length)) {
    tone = "#ef4444"; label = "Pipeline unknown";
  } else if (runs) {
    const last = runs.runs[0];
    const ok = last.status === "success";
    const hours = (Date.now() - new Date(last.started_at).getTime()) / 36e5;
    const age = hours < 1 ? "just now" : hours < 48 ? `${Math.round(hours)}h ago` : `${Math.round(hours / 24)}d ago`;
    // Three states: "succeeded" and "fresh" are different claims.
    tone = !ok ? "#ef4444" : hours > STALE_AFTER_HOURS ? "#f59e0b" : "#d8f5a9";
    label = !ok ? "Pipeline failed" : hours > STALE_AFTER_HOURS ? `Data stale · ${age}` : `Live · ${age}`;
    title = `Last run ${new Date(last.started_at).toLocaleString()} · ${last.status} · ${last.detections?.toLocaleString() ?? "—"} detections`;
  }
  return (
    <span title={title} class="hidden sm:inline-flex items-center gap-2 h-8 px-2.5 border-2 text-[11px] font-extrabold tracking-[0.06em] uppercase"
          style={`border-color:${tone};color:${tone}`}>
      <span class="w-2 h-2" style={`background:${tone}`} />{label}
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
    <button onClick={flip} aria-label="Toggle theme"
            class="inline-flex items-center gap-1.5 h-8 px-2.5 bg-[#18181b] text-white border-2 border-[#3f3f46] text-[11px] font-extrabold tracking-[0.06em] uppercase cursor-pointer">
      <Icon name={dark ? "light_mode" : "dark_mode"} style="font-size:15px" />{dark ? "Light" : "Dark"}
    </button>
  );
}

function Wordmark() {
  return (
    <button onClick={() => go("dashboard")} class="flex items-center gap-2.5 bg-transparent border-0 cursor-pointer p-0">
      <span class="w-8 h-8 border-2 border-[#d8f5a9] flex items-center justify-center">
        <span class="w-3.5 h-3.5 rounded-full border-2 border-[#d8f5a9] flex items-center justify-center">
          <span class="w-1 h-1 rounded-full bg-[#ef4444]" />
        </span>
      </span>
      <span class="text-[18px] font-black tracking-[0.08em] text-white">THERMO<span class="text-[#d8f5a9]">STATS</span></span>
    </button>
  );
}

export function Shell({ route, children }) {
  // Desktop starts open; phones start closed and the drawer overlays.
  const [open, setOpen] = useState(() => window.innerWidth >= 1024);
  const pick = (id) => { go(id); if (window.innerWidth < 1024) setOpen(false); };

  return (
    <div class="min-h-screen flex flex-col">
      <header class="sticky top-0 z-[1000] bg-[var(--color-bar)] h-14 px-3 flex items-center gap-3 border-b-2 border-black">
        <button onClick={() => setOpen(!open)} aria-label={open ? "Close navigation" : "Open navigation"}
                class="w-9 h-9 flex items-center justify-center bg-[#18181b] text-white border-2 border-[#3f3f46] cursor-pointer">
          <Icon name={open ? "close" : "menu"} />
        </button>
        <Wordmark />
        <div class="ml-auto flex items-center gap-2">
          <PipelineChip />
          <button onClick={() => location.reload()} class="btn-accent inline-flex items-center gap-1.5 h-8 px-2.5 border-2 border-[#d8f5a9] text-[11px] font-extrabold tracking-[0.06em] uppercase cursor-pointer">
            <Icon name="sync" style="font-size:15px" />Sync
          </button>
          <ThemeToggle />
        </div>
      </header>

      <div class="flex flex-1 min-h-0">
        {open && (
          <aside class="fixed lg:sticky top-14 z-[900] h-[calc(100vh-56px)] w-[248px] shrink-0 overflow-y-auto bg-[var(--color-panel)] border-r-2 border-rule py-4 px-3">
            {NAV.map((g) => (
              <nav key={g.group} class="mb-5">
                <p class="label-caps m-0 mb-2 px-2 text-muted">{g.group}</p>
                {g.items.map((it) => {
                  const on = it.id === route.page;
                  return (
                    <button key={it.id} onClick={() => pick(it.id)}
                            class="w-full flex items-center gap-3 px-3 py-2.5 mb-1 border-2 text-left text-[12px] font-extrabold tracking-[0.05em] uppercase cursor-pointer"
                            style={on ? "background:var(--color-bar);color:#fff;border-color:var(--color-bar);box-shadow:3px 3px 0 var(--color-accent)"
                                      : "background:transparent;color:var(--color-ink);border-color:transparent"}>
                      <Icon name={it.icon} style="font-size:18px" />{it.label}
                    </button>
                  );
                })}
              </nav>
            ))}
          </aside>
        )}
        <main class="flex-1 min-w-0 px-5 lg:px-8 py-6">
          <div class="max-w-[1400px] mx-auto">{children}</div>
          <footer class="max-w-[1400px] mx-auto mt-12 pt-4 border-t-2 border-rule flex justify-between gap-4 flex-wrap text-[11px] font-bold tracking-[0.06em] uppercase text-muted">
            <span>ThermoStats · SIH26162 · NASA FIRMS VIIRS NOAA-20</span>
            <span>OSM · WRI · Smithsonian GVP · IHS v3.0</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

export function ErrorScreen({ message }) {
  return (
    <div class="panel p-8 text-center max-w-[560px] mx-auto mt-16">
      <Icon name="cloud_off" style="font-size:30px;color:var(--color-high)" />
      <h2 class="text-[18px] font-black tracking-[0.06em] uppercase mt-3 mb-1">Cannot reach the API</h2>
      <p class="text-[13px] text-muted mb-4">{message}</p>
      <code class="mono block text-[11px] bg-[var(--color-wash)] border-2 border-rule p-2.5 text-left">
        ML\.venv\Scripts\python.exe -m uvicorn backend.app:app --port 8000
      </code>
    </div>
  );
}
