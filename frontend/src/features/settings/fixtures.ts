import type { MeView, UserView } from "../../api/types";
import type { AuthenticatedSession } from "../../auth/session";

export const HOSTILE_USERNAME = "<img src=x onerror=alert(1)>";

export function userFixture(overrides: Partial<UserView> = {}): UserView {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    username: "alice",
    role: "viewer",
    disabled: false,
    created_at: "2026-10-01T10:00:00Z",
    last_login_at: null,
    ...overrides,
  };
}

export function sessionFor(me: MeView): AuthenticatedSession {
  return { status: "authenticated", me, login: async () => undefined, logout: () => undefined, retry: () => undefined };
}
