import { Navigate, Outlet, Route, Routes, useParams } from "react-router";
import { RequireAuth } from "./auth/RequireAuth";
import { useSessionState } from "./auth/session";
import { StreamConnectedContext, useEventStream } from "./live/useEventStream";
import { ActivityPage } from "./pages/ActivityPage";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ServerPage } from "./pages/ServerPage";
import { ServersPage } from "./pages/ServersPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SystemPage } from "./pages/SystemPage";
import { UiKitPage } from "./pages/UiKitPage";
import { AppShell } from "./shell/AppShell";

function TraceRedirect() {
  const { id = "" } = useParams();
  return <Navigate to={`/incidents/${encodeURIComponent(id)}?tab=activity`} replace />;
}

export function App() {
  const { status } = useSessionState();
  const connected = useEventStream(status === "authenticated");

  return (
    <StreamConnectedContext.Provider value={connected}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <RequireAuth>
              <AppShell>
                <Outlet />
              </AppShell>
            </RequireAuth>
          }
        >
          <Route path="/" element={<OverviewPage />} />
          <Route path="/incidents" element={<IncidentsPage />} />
          <Route path="/incidents/:id" element={<IncidentDetailPage />} />
          <Route path="/incidents/:id/trace" element={<TraceRedirect />} />
          <Route path="/targets" element={<Navigate to="/servers" replace />} />
          <Route path="/servers" element={<ServersPage />} />
          <Route path="/servers/:id" element={<ServerPage />} />
          <Route path="/system" element={<SystemPage />} />
          <Route path="/activity" element={<ActivityPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          {import.meta.env.DEV && <Route path="/__ui" element={<UiKitPage />} />}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </StreamConnectedContext.Provider>
  );
}
