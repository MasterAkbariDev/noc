import { lazy, useEffect } from "react";
import { Navigate, Outlet, Route, Routes, useParams } from "react-router";
import { RequireAuth } from "./auth/RequireAuth";
import { useSessionState } from "./auth/session";
import { StreamConnectedContext, useEventStream } from "./live/useEventStream";
import { ActivityPage } from "./pages/ActivityPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { LoginPage } from "./pages/LoginPage";
import { MetricsPage } from "./pages/MetricsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ServerPage } from "./pages/ServerPage";
import { ServersPage } from "./pages/ServersPage";
import { SystemPage } from "./pages/SystemPage";
import { AppShell } from "./shell/AppShell";

const loadIncidentDetailPage = () =>
  import("./pages/IncidentDetailPage").then((module) => ({ default: module.IncidentDetailPage }));
const loadSettingsPage = () => import("./pages/SettingsPage").then((module) => ({ default: module.SettingsPage }));

const PAGE_LOADERS = [loadIncidentDetailPage, loadSettingsPage];

const FleetPage = lazy(() => import("./pages/FleetPage").then((module) => ({ default: module.FleetPage })));
const IncidentDetailPage = lazy(loadIncidentDetailPage);
const NotFoundPage = lazy(() => import("./pages/NotFoundPage").then((module) => ({ default: module.NotFoundPage })));
const SettingsPage = lazy(loadSettingsPage);
const UiKitPage = import.meta.env.DEV
  ? lazy(() => import("./pages/UiKitPage").then((module) => ({ default: module.UiKitPage })))
  : null;

function TraceRedirect() {
  const { id = "" } = useParams();
  return <Navigate to={`/incidents/${encodeURIComponent(id)}?tab=activity`} replace />;
}

export function App() {
  const { status } = useSessionState();
  const connected = useEventStream(status === "authenticated");

  useEffect(() => {
    if (status === "authenticated") {
      PAGE_LOADERS.forEach((load) => void load());
    }
  }, [status]);

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
          <Route path="/fleet" element={<FleetPage />} />
          <Route path="/activity" element={<ActivityPage />} />
          <Route path="/stats" element={<MetricsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          {UiKitPage !== null && <Route path="/__ui" element={<UiKitPage />} />}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </StreamConnectedContext.Provider>
  );
}
