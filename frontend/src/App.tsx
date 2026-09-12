import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import { AssumptionStrip } from "./components/AssumptionStrip";
import { useRunState, THRESHOLDS } from "./state";
import Ledger from "./pages/Ledger";
import ObjectCard from "./pages/ObjectCard";
import EventConsole from "./pages/EventConsole";
import Shells from "./pages/Shells";
import Deploy from "./pages/Deploy";
import Bench from "./pages/Bench";
import Provenance from "./pages/Provenance";
import Globe from "./pages/Globe";
import type { Envelope } from "./api/types";

interface Health {
  status: string;
  version: string;
  propagator: string;
  demo_safe: boolean;
  runs_available: string[];
  data_freshness: { catalogue_epoch_age_h: number | null; last_screening_run: string | null; n_objects: number };
}

const TABS = [
  ["/globe", "GLOBE"],
  ["/ledger", "WHO PAYS · ledger"],
  ["/cluster", "DECIDE · event console"],
  ["/shells", "WHERE TO FLY · shell map"],
  ["/deploy", "NEW CONSTELLATION · deployment"],
  ["/bench", "PROOF · benchmark"],
  ["/provenance", "ASSUMPTIONS · provenance"],
] as const;

export default function App() {
  const { runId, pcThreshold, set } = useRunState();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<Health>("/health"),
    refetchInterval: 30_000,
  });
  const h = health.data?.data;
  const runs = h?.runs_available ?? [];
  const current = runId ?? health.data?.run_id ?? "";
  const fresh = h?.data_freshness.catalogue_epoch_age_h;

  return (
    <div className="app">
      <div className="topbar">
        <span className="brand">ORBITAL CAPACITY <span>INTELLIGENCE</span></span>
        <span className="sep">│</span>
        <span className="ctl">
          <label>run</label>
          <select value={current} onChange={(e) => set({ run: e.target.value })}>
            {runs.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </span>
        <span className="ctl">
          <label>Pc*</label>
          <span className="seg">
            {THRESHOLDS.map((t) => (
              <button key={t} className={t === pcThreshold ? "on" : ""} onClick={() => set({ thr: t })}>
                {t.toExponential(0)}
              </button>
            ))}
          </span>
        </span>
        <span className="right">
          {h?.demo_safe && <span className="pill warn">DEMO-SAFE · OFFLINE</span>}
          <span>
            <span className={`dot ${health.isError ? "bad" : fresh != null && fresh > 48 ? "warn" : "ok"}`} />
            {health.isError
              ? "api down"
              : fresh != null
                ? `elements ${fresh.toFixed(0)} h old`
                : "—"}
          </span>
          <span>{h?.data_freshness.n_objects?.toLocaleString() ?? "—"} objects</span>
          <span className="sep">│</span>
          <span>v{h?.version ?? "—"}</span>
        </span>
      </div>

      <AssumptionStrip a={health.data?.assumptions} />

      <nav className="nav">
        {TABS.map(([to, label]) => (
          <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "on" : "")}>
            {label}
          </NavLink>
        ))}
      </nav>

      <main className={"main" + (useLocation().pathname.startsWith("/globe") ? " flush" : "")}>
        <Routes>
          <Route path="/" element={<Navigate to="/globe" replace />} />
          <Route path="/globe" element={<Globe />} />
          <Route path="/ledger" element={<Ledger />} />
          <Route path="/object/:id" element={<ObjectCard />} />
          <Route path="/cluster" element={<EventConsole />} />
          <Route path="/cluster/:id" element={<EventConsole />} />
          <Route path="/shells" element={<Shells />} />
          <Route path="/deploy" element={<Deploy />} />
          <Route path="/bench" element={<Bench />} />
          <Route path="/provenance" element={<Provenance />} />
        </Routes>
      </main>
    </div>
  );
}
