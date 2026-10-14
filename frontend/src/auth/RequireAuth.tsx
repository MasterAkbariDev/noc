import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { ErrorState } from "../ui/ErrorState";
import { Skeleton } from "../ui/Skeleton";
import { loginRoute, useSessionState } from "./session";

export function RequireAuth({ children }: { children: ReactNode }) {
  const session = useSessionState();
  const location = useLocation();

  if (session.status === "loading") {
    return (
      <div className="mx-auto w-full max-w-6xl p-4 md:p-6">
        <Skeleton lines={4} />
      </div>
    );
  }
  if (session.status === "unreachable") {
    return (
      <div className="mx-auto w-full max-w-xl p-4 md:p-6">
        <ErrorState
          title="The NOC is not reachable"
          message="The panel could not ask the NOC who is signed in. Check that the NOC is running and the SSH tunnel is open, then retry."
          onRetry={session.retry}
        />
      </div>
    );
  }
  if (session.status === "anonymous") {
    return <Navigate to={loginRoute(`${location.pathname}${location.search}`)} replace />;
  }
  return children;
}
