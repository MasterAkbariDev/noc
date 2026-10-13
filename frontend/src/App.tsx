import { Link, Navigate, Route, Routes } from "react-router";
import { TokenBar } from "./components/TokenBar";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { IncidentsPage } from "./pages/IncidentsPage";

export function App() {
  return (
    <div className="app">
      <header className="app-header">
        <Link to="/incidents" className="brand">
          Multi-Agent NOC
        </Link>
        <TokenBar />
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/incidents" replace />} />
          <Route path="/incidents" element={<IncidentsPage />} />
          <Route path="/incidents/:id" element={<IncidentDetailPage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
