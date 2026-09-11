import { useEffect, useState } from "preact/hooks";
import { api } from "../api.js";
import { Icon, Pill } from "./ui.jsx";

// Only pages that actually exist get a nav entry. "place" is reachable from
// the alert feed but has no page of its own yet, so it stays out of here.
export const PAGES = [
  { id: "industrial", label: "Industrial sources" },
  { id: "fires", label: "Active fires" },
  { id: "classification", label: "Classification" },
  { id: "model", label: "Model report" },
];

// A run older than this is shown as stale. The job fires daily at 05:00 IST;
// 26 hours leaves slack for a late start without letting a dead scheduler
// hide behind a green badge - which is exactly how a 07:00 IST misconfiguration
// once went unnoticed while the dashboard looked perfectly healthy.
const STALE_AFTER_HOURS = 26;

/** Wordmark: a thermal aperture mark, per the Stitch logo. */
function Wordmark() {
  return (
    <div class="flex items-center gap-2.5 shrink-0">
      <span class="w-7 h-7 rounded-[7px] bg-ink flex items-center justify-center">
        <span class="w-3 h-3 rounded-full border-2 border-white flex items-center justify-center">
          <span class="w-1 h-1 rounded-full bg-high" />
        </span>
      </span>
      <span class="text-[17px] font-bold tracking-[-0.02em]">ThermoStats</span>
    </div>
  );
}

function PipelineChip() {
  const [runs, setRuns] = useState(null);

  useEffect(() => {
    api.runs(1).then(setRuns).catch(() => setRuns({ error: true }));
  }, []);

  if (!runs) {
    return <Pill dot tone="#64748b">Checking pipeline</Pill>;
  }
  if (runs.error || !runs.runs?.length) {
    return <Pill dot tone="#dc2626">Pipeline unknown</Pill>;
  }

  const last = runs.runs[0];
  const ok = last.status === "success";
  const ageHours = (Date.now() - new Date(last.started_at).getTime()) / 36e5;
  const stale = ok && ageHours > STALE_AFTER_HOURS;
  const when = new Date(last.started_at).toLocaleString(undefined, {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
  const age = ageHours < 1 ? "just now"
    : ageHours < 48 ? `${Math.round(ageHours)}h ago`
    : `${Math.round(ageHours / 24)} days ago`;

  // Three states, not two. "Succeeded" and "fresh" are different claims, and
  // conflating them is what let a stopped scheduler look healthy.
  const tone = !ok ? "#dc2626" : stale ? "#d97706" : "#16a34a";
  const label = !ok
    ? `Pipeline failed · ${when}`
    : stale
      ? `Data stale · last run ${age}`
      : `Pipeline ok · ${when} · ${last.seconds ?? "—"}s`;

  return (
    <span title={`Last run ${when} (${age}). Status: ${last.status}.`}>
      <Pill dot tone={tone}>{label}</Pill>
    </span>
  );
}

export function Shell({ page, onNavigate, children }) {
  return (
    <div class="min-h-screen flex flex-col">
      <header class="bg-panel border-b border-rule sticky top-0 z-[500]">
        <div class="max-w-[1600px] mx-auto px-5 pt-3 flex items-center gap-5 flex-wrap">
          <Wordmark />
          <p class="text-[13px] text-muted m-0 flex-1 min-w-[200px]">
            Persistent thermal sources from NASA FIRMS, scored on a year of
            behaviour
          </p>
          <PipelineChip />
        </div>

        <nav class="max-w-[1600px] mx-auto px-5 flex gap-1 mt-1.5">
          {PAGES.map((p) => {
            const active = p.id === page;
            return (
              <button
                key={p.id}
                onClick={() => onNavigate(p.id)}
                class="bg-transparent border-0 font-sans text-[13px] font-semibold px-3 py-2.5 cursor-pointer -mb-px border-b-2 transition-colors"
                style={
                  active
                    ? "color:#0f172a;border-bottom-color:#0f172a"
                    : "color:#64748b;border-bottom-color:transparent"
                }
              >
                {p.label}
              </button>
            );
          })}
        </nav>
      </header>

      <main class="flex-1 max-w-[1600px] w-full mx-auto px-5 py-4">
        {children}
      </main>

      <footer class="border-t border-rule mt-4">
        <div class="max-w-[1600px] mx-auto px-5 py-3.5 flex justify-between gap-4 flex-wrap text-[12px] text-muted">
          <span class="flex items-center gap-2">
            ThermoStats Scientific Observation Node
            <span class="text-edge">•</span>
            NASA FIRMS Calibration Feed
          </span>
          <span>Place-level model v2 · 687,289 reference places</span>
        </div>
      </footer>
    </div>
  );
}

export function ErrorScreen({ message }) {
  return (
    <div class="panel p-8 text-center max-w-[560px] mx-auto mt-16">
      <Icon name="cloud_off" style="font-size:28px;color:#dc2626" />
      <h2 class="text-[16px] font-semibold mt-3 mb-1">Cannot reach the API</h2>
      <p class="text-[12px] text-muted mb-4">{message}</p>
      <code class="block text-[11px] bg-wash border border-rule rounded-[6px] p-2.5 text-left">
        ML\.venv\Scripts\python.exe -m uvicorn backend.app:app --reload
      </code>
    </div>
  );
}
