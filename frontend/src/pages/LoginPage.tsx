import { useState, type FormEvent } from "react";
import { Navigate, useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import { useSessionState } from "../auth/session";
import { safeNext } from "../auth/safeNext";
import { Button } from "../ui/Button";

const FIELD_MAX_LENGTH = 256;
const INPUT_CLASS =
  "rounded-control border border-border bg-bg px-3 py-2 text-fg placeholder:text-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

function loginFailureText(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return "Invalid username or password.";
  }
  if (error instanceof ApiError && error.status === 429) {
    return "Too many attempts. Wait 15 minutes and try again.";
  }
  return "Could not reach the NOC. Try again.";
}

export function LoginPage() {
  const session = useSessionState();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const expired = params.get("expired") === "1";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  if (session.status === "authenticated") {
    return <Navigate to={next} replace />;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setFailure(null);
    try {
      await session.login(username.trim(), password);
    } catch (error) {
      setFailure(loginFailureText(error));
      setPassword("");
    } finally {
      setPending(false);
    }
  }

  return (
    <main id="main" tabIndex={-1} className="grid min-h-screen place-items-center bg-bg p-4">
      <section aria-labelledby="login-title" className="w-full max-w-sm rounded-card border border-border bg-surface p-6 shadow-card">
        <p className="text-sm font-medium text-muted">Multi-Agent NOC</p>
        <h1 id="login-title" className="mt-1 text-xl font-semibold text-fg">
          Sign in
        </h1>
        {expired && (
          <p role="status" className="mt-4 rounded-control bg-warning-soft px-3 py-2 text-sm text-fg">
            Your session expired. Sign in again.
          </p>
        )}
        <form className="mt-6 grid gap-4" onSubmit={submit}>
          <label className="grid gap-1 text-sm font-medium text-fg">
            Username
            <input
              name="username"
              type="text"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              required
              maxLength={FIELD_MAX_LENGTH}
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          <label className="grid gap-1 text-sm font-medium text-fg">
            Password
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={FIELD_MAX_LENGTH}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={INPUT_CLASS}
            />
          </label>
          {failure !== null && (
            <p role="alert" className="text-sm text-critical">
              {failure}
            </p>
          )}
          <Button type="submit" variant="primary" disabled={pending}>
            {pending ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </section>
    </main>
  );
}
