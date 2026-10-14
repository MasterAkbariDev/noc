import { lazy } from "react";
import { Navigate, Outlet, Route, Routes, useParams } from "react-router";
import { RequireAuth } from "./auth/RequireAuth";
import { useSessionState } from "./auth/session";
import { StreamConnectedContext, useEventStream } from "./live/useEventStream";
import { LoginPage } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { AppShell } from "./shell/AppShell";

const ActivityPage = lazy(() => import("./pages/ActivityPage").then((module) => ({ default: module.ActivityPage })));
const IncidentDetailPage = lazy(() =>
  import("./pages/IncidentDetailPage").then((module) => ({ default: module.IncidentDetailPage })),
);
const IncidentsPage = lazy(() => import("./pages/IncidentsPage").then((module) => ({ default: module.IncidentsPage })));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage").then((module) => ({ default: module.NotFoundPage })));
const ServerPage = lazy(() => import("./pages/ServerPage").then((module) => ({ default: module.ServerPage })));
const ServersPage = lazy(() => import("./pages/ServersPage").then((module) => ({ default: module.ServersPage })));
const SettingsPage = lazy(() => import("./pages/SettingsPage").then((module) => ({ default: module.SettingsPage })));
const SystemPage = lazy(() => import("./pages/SystemPage").then((module) => ({ default: module.SystemPage })));
const UiKitPage = lazy(() => import("./pages/UiKitPage").then((module) => ({ default: module.UiKitPage })));

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
