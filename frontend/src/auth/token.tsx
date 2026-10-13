import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export const TOKEN_STORAGE_KEY = "noc.apiToken";

type TokenState = {
  token: string;
  saveToken: (next: string) => void;
  clearToken: () => void;
};

const TokenContext = createContext<TokenState | null>(null);

export function readStoredToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function writeStoredToken(value: string): void {
  try {
    if (value) {
      sessionStorage.setItem(TOKEN_STORAGE_KEY, value);
    } else {
      sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    return;
  }
}

export function TokenProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState(readStoredToken);

  const saveToken = useCallback((next: string) => {
    const trimmed = next.trim();
    writeStoredToken(trimmed);
    setToken(trimmed);
  }, []);

  const clearToken = useCallback(() => {
    writeStoredToken("");
    setToken("");
  }, []);

  const value = useMemo(() => ({ token, saveToken, clearToken }), [token, saveToken, clearToken]);

  return <TokenContext.Provider value={value}>{children}</TokenContext.Provider>;
}

export function useToken(): TokenState {
  const state = useContext(TokenContext);
  if (state === null) {
    throw new Error("useToken must be used inside TokenProvider");
  }
  return state;
}
