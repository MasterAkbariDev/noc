import type { MeView } from "../api/types";

type SessionState = {
  me: MeView;
  status: "authenticated";
  logout: () => void;
};

const STUB_ME: MeView = { username: "dev", role: "admin", via: "token" };

export function useSession(): SessionState {
  return { me: STUB_ME, status: "authenticated", logout: () => {} };
}
