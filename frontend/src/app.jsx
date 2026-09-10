import { useEffect, useState } from "preact/hooks";
import { api } from "./api.js";
import { Shell, ErrorScreen } from "./components/Shell.jsx";
import { Panel, Empty } from "./components/ui.jsx";
import { Industrial } from "./pages/Industrial.jsx";
import { Fires } from "./pages/Fires.jsx";
import { Classification } from "./pages/Classification.jsx";

/**
 * Place detail has no page of its own yet. The alert feed still offers an
 * "open place" action, so route it somewhere honest rather than nowhere.
 */
function PlaceStub({ cellId, onBack }) {
  return (
    <Panel title="Place detail"
           right={<button class="btn" onClick={onBack}>Back to sources</button>}>
      <Empty
        icon="construction"
        title="Not built yet"
        body={`Cell ${cellId ?? "—"} is selected. The per-place history view is
               still to come; the selection card on the sources page carries
               the scoring detail in the meantime.`}
      />
    </Panel>
  );
}

export function App() {
  const [page, setPage] = useState("industrial");
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);

  // One cheap probe so an unreachable API gets a real screen instead of an
  // empty shell. The pages fetch their own data independently of this.
  useEffect(() => {
    api.summary().catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorScreen message={error} />;

  return (
    <Shell page={page} onNavigate={setPage}>
      {page === "fires" ? (
        <Fires />
      ) : page === "classification" ? (
        <Classification selected={selected} onSelect={setSelected} />
      ) : page === "place" ? (
        <PlaceStub cellId={selected} onBack={() => setPage("industrial")} />
      ) : (
        <Industrial
          selected={selected}
          onSelect={setSelected}
          onOpenPlace={(cellId) => { setSelected(cellId); setPage("place"); }}
        />
      )}
    </Shell>
  );
}
