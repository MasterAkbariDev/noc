import { useState, type FormEvent } from "react";
import { Navigate, useSearchParams } from "react-router";
import { ApiError, TOTP_REQUIRED_DETAIL } from "../api/client";
import { useSessionState } from "../auth/session";
import { safeNext } from "../auth/safeNext";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { Radar } from "lucide-react";
import { Alert, Button, Field, Form, FormMessage, TextInput } from "../ui";

const FIELD_MAX_LENGTH = 256;

const CODE_MAX_LENGTH = 16;

function isCodeRequest(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401 && error.detail === TOTP_REQUIRED_DETAIL;
}

function loginFailureText(error: unknown, codeStep: boolean): string {
  if (error instanceof ApiError && error.status === 401 && codeStep) {
    return "That code was not accepted. Wait for the next one and try again.";
  }
  if (error instanceof ApiError && error.status === 401) {
    return "Invalid username or password.";
  }
  if (error instanceof ApiError && error.status === 403) {
    return error.detail;
  }
  if (error instanceof ApiError && error.status === 429) {
    return "Too many attempts. Wait 15 minutes and try again.";
  }
  return "Could not reach the NOC. Try again.";
}

export function LoginPage() {
  useDocumentTitle("Sign in");
  const session = useSessionState();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const expired = params.get("expired") === "1";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [codeStep, setCodeStep] = useState(false);
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
      await session.login(username.trim(), password, codeStep ? code.trim() : undefined);
    } catch (error) {
      if (isCodeRequest(error)) {
        setCodeStep(true);
      } else {
        setFailure(loginFailureText(error, codeStep));
        setCode("");
        if (!codeStep) {
          setPassword("");
        }
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <main id="main" tabIndex={-1} className="grid min-h-screen place-items-center bg-bg p-4">
      <section aria-labelledby="login-title" className="page-enter w-full max-w-sm rounded-card border border-border bg-surface p-8 shadow-raised">
        <div className="flex items-center gap-2.5">
          <span aria-hidden="true" className="inline-grid size-9 place-items-center rounded-full bg-accent text-accent-fg">
            <Radar size={20} strokeWidth={2.25} />
          </span>
          <p className="m-0 text-sm font-semibold text-muted">Multi-Agent NOC</p>
        </div>
        <h1 id="login-title" className="mt-6 mb-0 text-2xl font-semibold tracking-tight text-fg">
          Sign in
        </h1>
        <p className="m-0 mt-1 text-muted">See what your servers are doing and what the NOC fixed for you. Use the account an admin made for you.</p>
        {expired && (
          <div className="mt-4">
            <Alert tone="warning" role="status">
              <p className="m-0">Your session expired. Sign in again.</p>
            </Alert>
          </div>
        )}
        <Form className="mt-6" onSubmit={submit}>
          <Field label="Username">
            <TextInput
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              required
              maxLength={FIELD_MAX_LENGTH}
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </Field>
          <Field label="Password">
            <TextInput
              name="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={FIELD_MAX_LENGTH}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          {codeStep && (
            <Field label="Authentication code">
              <TextInput
                name="totp"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                autoFocus
                maxLength={CODE_MAX_LENGTH}
                value={code}
                onChange={(event) => setCode(event.target.value)}
              />
            </Field>
          )}
          {failure !== null && <FormMessage>{failure}</FormMessage>}
          <Button type="submit" variant="primary" disabled={pending} className="w-full justify-self-stretch">
            {pending ? "Signing in…" : "Sign in"}
          </Button>
        </Form>
      </section>
    </main>
  );
}
