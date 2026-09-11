import { useEffect, useState } from "preact/hooks";
import { api } from "./api.js";
import { Shell, ErrorScreen } from "./components/Shell.jsx";
import { useRoute, go } from "./components/layout.jsx";
import { Dashboard } from "./pages/Dashboard.jsx";
import { Search } from "./pages/Search.jsx";
import { Investigation } from "./pages/Investigation.jsx";
import { Assessment } from "./pages/Assessment.jsx";
import { Anomaly } from "./pages/Anomaly.jsx";
import { Alerts } from "./pages/Alerts.jsx";
import { Fires } from "./pages/Fires.jsx";
import { Classification } from "./pages/Classification.jsx";
import { Reports } from "./pages/Reports.jsx";
import { DataLayers } from "./pages/DataLayers.jsx";
import { System } from "./pages/System.jsx";

// Selecting a source anywhere opens its investigation page.
const openSource = (cellId) => cellId && go(`investigation/${cellId}`);

const PAGES = {
  dashboard: Dashboard, search: Search, investigation: Investigation,
  assessment: Assessment, anomaly: Anomaly, alerts: Alerts, fires: Fires,
  classification: Classification, reports: Reports, layers: DataLayers,
  system: System,
};

export function App() {
  const route = useRoute();
  const [error, setError] = useState(null);

  // One cheap probe so an unreachable API gets a real screen, not an empty shell.
  useEffect(() => { api.summary().catch((e) => setError(e.message)); }, []);

  const Page = PAGES[route.page] || Dashboard;
  return (
    <Shell route={route}>
      {error ? <ErrorScreen message={error} />
             : <Page route={route} selected={route.param ? Number(route.param) : null} onSelect={openSource} />}
    </Shell>
  );
}
