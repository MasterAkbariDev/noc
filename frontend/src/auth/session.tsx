import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import {
  ApiError,
  getMe,
  login as loginRequest,
  logout as logoutRequest,
  setUnauthorizedHandler,
} from "../api/client";
import type { MeView } from "../api/types";

export const ME_QUERY_KEY = "me";

type SessionActions = {
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
};

export type SessionState =
  | ({ status: "loading"; me: null } & SessionActions)
  | ({ status: "anonymous"; me: null } & SessionActions)
  | ({ status: "authenticated"; me: MeView } & SessionActions);

export type AuthenticatedSession = Extract<SessionState, { status: "authenticated" }>;

type SessionReading = { status: "loading" | "anonymous"; me: null } | { status: "authenticated"; me: MeView };

const SessionContext = createContext<SessionState | null>(null);

export function loginRoute(next: string | undefined, expired = false): string {
  const params = new URLSearchParams();
  if (expired) {
    params.set("expired", "1");
  }
  if (next !== undefined && !next.startsWith("/login")) {
    params.set("next", next);
  }
  const query = params.toString();
  return query === "" ? "/login" : `/login?${query}`;
}

function isRejected(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

function readSession(query: { data: MeView | null | undefined; error: unknown; isPending: boolean }): SessionReading {
  if (isRejected(query.error)) {
    return { status: "anonymous", me: null };
  }
  if (query.data) {
    return { status: "authenticated", me: query.data };
  }
  if (query.isPending) {
    return { status: "loading", me: null };
  }
  return { status: "anonymous", me: null };
}

function replaceSession(queryClient: QueryClient, me: MeView | null): void {
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== ME_QUERY_KEY });
  queryClient.setQueryData<MeView | null>([ME_QUERY_KEY], me);
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const here = `${location.pathname}${location.search}`;

  const query = useQuery<MeView | null>({
    queryKey: [ME_QUERY_KEY],
    queryFn: getMe,
    retry: false,
  });

  const login = useCallback(
    async (username: string, password: string) => {
      const me = await loginRequest(username, password);
      replaceSession(queryClient, me);
    },
    [queryClient],
  );

  const logout = useCallback(() => {
    void logoutRequest()
      .catch(() => undefined)
      .finally(() => {
        replaceSession(queryClient, null);
        navigate("/login", { replace: true });
      });
  }, [navigate, queryClient]);

  const expire = useCallback(() => {
    replaceSession(queryClient, null);
    navigate(loginRoute(here, true), { replace: true });
  }, [here, navigate, queryClient]);

  useEffect(() => {
    setUnauthorizedHandler(expire);
    return () => setUnauthorizedHandler(null);
  }, [expire]);

  const value: SessionState = { ...readSession(query), login, logout };

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSessionState(): SessionState {
  const state = useContext(SessionContext);
  if (state === null) {
    throw new Error("useSessionState must be used inside SessionProvider");
  }
  return state;
}

export function useSession(): AuthenticatedSession {
  const state = useSessionState();
  if (state.status !== "authenticated") {
    throw new Error("useSession must be used inside RequireAuth");
  }
  return state;
}
