import { Link, NavLink, Navigate, Route, Routes } from "react-router";
import { useToken } from "./auth/token";
import { ThemeToggle } from "./components/ThemeToggle";
import { TokenBar } from "./components/TokenBar";
import { StreamConnectedContext, useEventStream } from "./live/useEventStream";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { TargetsPage } from "./pages/TargetsPage";
import { TracePage } from "./pages/TracePage";
import { UiKitPage } from "./pages/UiKitPage";

export function App() {
  const { token } = useToken();
  const connected = useEventStream(token);

  return (
    <StreamConnectedContext.Provider value={connected}>
      <div className="app">
        <header className="app-header">
          <Link to="/incidents" className="brand">
            Multi-Agent NOC
          </Link>
          <nav className="app-nav" aria-label="Main">
            <NavLink to="/incidents">Incidents</NavLink>
            <NavLink to="/targets">Targets</NavLink>
          </nav>
          <ThemeToggle />
          <TokenBar />
        </header>
        <main>
          <Routes>
            <Route path="/" element={<Navigate to="/incidents" replace />} />
            <Route path="/incidents" element={<IncidentsPage />} />
            <Route path="/incidents/:id" element={<IncidentDetailPage />} />
            <Route path="/incidents/:id/trace" element={<TracePage />} />
            <Route path="/targets" element={<TargetsPage />} />
            {import.meta.env.DEV && <Route path="/__ui" element={<UiKitPage />} />}
            <Route path="*" element={<p>Page not found.</p>} />
          </Routes>
        </main>
      </div>
    </StreamConnectedContext.Provider>
  );
}
