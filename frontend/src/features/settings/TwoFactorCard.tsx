import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { totpDisable, totpEnable, totpSetup } from "../../api/client";
import type { TotpSetup } from "../../api/types";
import { useSession } from "../../auth/session";
import { Button } from "../../ui/Button";
import { useToast } from "../../ui/Toaster";
import { settingsErrorText } from "./accountView";
import { INPUT_CLASS, LABEL_CLASS } from "./formStyles";

const CODE_MAX_LENGTH = 16;
const PASSWORD_MAX_LENGTH = 256;

function StartForm({ onStarted }: { onStarted: (setup: TotpSetup) => void }) {
  const [password, setPassword] = useState("");
  const mutation = useMutation({
    mutationFn: (currentPassword: string) => totpSetup(currentPassword),
    onSuccess: (setup) => {
      setPassword("");
      onStarted(setup);
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate(password);
  }

  return (
    <form onSubmit={submit} className="grid max-w-md gap-4">
      <p className="m-0 text-sm text-muted">
        Two-factor authentication asks for a six-digit code from an authenticator app after your password. Confirm your
        password to start.
      </p>
      <label className={LABEL_CLASS}>
        Current password
        <input
          name="totp-current-password"
          type="password"
          autoComplete="current-password"
          required
          maxLength={PASSWORD_MAX_LENGTH}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      {mutation.isError && (
        <p role="alert" className="m-0 text-sm text-critical">
          {settingsErrorText(mutation.error)}
        </p>
      )}
      <div>
        <Button type="submit" variant="primary" disabled={mutation.isPending}>
          Start setup
        </Button>
      </div>
    </form>
  );
}

function ConfirmForm({ setup, onEnabled }: { setup: TotpSetup; onEnabled: () => void }) {
  const [code, setCode] = useState("");
  const mutation = useMutation({ mutationFn: (value: string) => totpEnable(value), onSuccess: onEnabled });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate(code.trim());
  }

  return (
    <form onSubmit={submit} className="grid max-w-md gap-4">
      <p className="m-0 text-sm text-muted">
        Add this account to your authenticator app, using the secret below or the setup address, then type the code it
        shows.
      </p>
      <dl className="m-0 grid gap-1 text-sm">
        <dt className="text-muted">Secret</dt>
        <dd className="m-0 font-mono break-all select-all">{setup.secret}</dd>
        <dt className="mt-2 text-muted">Setup address</dt>
        <dd className="m-0 font-mono text-xs break-all select-all">{setup.uri}</dd>
      </dl>
      <label className={LABEL_CLASS}>
        Code from the app
        <input
          name="totp-code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          required
          maxLength={CODE_MAX_LENGTH}
          value={code}
          onChange={(event) => setCode(event.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      {mutation.isError && (
        <p role="alert" className="m-0 text-sm text-critical">
          {settingsErrorText(mutation.error)}
        </p>
      )}
      <div>
        <Button type="submit" variant="primary" disabled={mutation.isPending}>
          Turn on
        </Button>
      </div>
    </form>
  );
}

function DisableForm({ onDisabled }: { onDisabled: () => void }) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const mutation = useMutation({
    mutationFn: ({ currentPassword, value }: { currentPassword: string; value: string }) =>
      totpDisable(currentPassword, value),
    onSuccess: onDisabled,
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate({ currentPassword: password, value: code.trim() });
  }

  return (
    <form onSubmit={submit} className="grid max-w-md gap-4">
      <label className={LABEL_CLASS}>
        Current password
        <input
          name="totp-disable-password"
          type="password"
          autoComplete="current-password"
          required
          maxLength={PASSWORD_MAX_LENGTH}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      <label className={LABEL_CLASS}>
        A new code from the app
        <input
          name="totp-disable-code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          required
          maxLength={CODE_MAX_LENGTH}
          value={code}
          onChange={(event) => setCode(event.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      {mutation.isError && (
        <p role="alert" className="m-0 text-sm text-critical">
          {settingsErrorText(mutation.error)}
        </p>
      )}
      <div>
        <Button type="submit" variant="danger" disabled={mutation.isPending}>
          Turn off
        </Button>
      </div>
    </form>
  );
}

export function TwoFactorCard() {
  const { me, retry, logout } = useSession();
  const toast = useToast();
  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const enabled = me.totp_enabled === true;
  const required = me.totp_required === true;

  function turnedOn() {
    setSetup(null);
    toast.success("Two-factor authentication is on. Your other sessions are signed out.");
    retry();
  }

  function turnedOff() {
    toast.success("Two-factor authentication is off. Sign in again.");
    logout();
  }

  let body = <StartForm onStarted={setSetup} />;
  if (setup !== null) {
    body = <ConfirmForm setup={setup} onEnabled={turnedOn} />;
  } else if (enabled && required) {
    body = <p className="m-0 text-sm text-muted">Your role must use two-factor authentication, so it cannot be turned off here.</p>;
  } else if (enabled) {
    body = <DisableForm onDisabled={turnedOff} />;
  }

  return (
    <div className="grid gap-4">
      <h3 className="m-0 text-base font-semibold">Two-factor authentication</h3>
      <p className="m-0 text-sm">
        Status: <span className="font-medium">{enabled ? "On" : "Off"}</span>
      </p>
      {body}
    </div>
  );
}
