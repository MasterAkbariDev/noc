import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { useState, type FormEvent } from "react";
import {
  getTelegram,
  removeTelegramToken,
  saveTelegram,
  setTelegramProxy,
  setTelegramToken,
  testTelegram,
} from "../../api/client";
import type {
  NotifyEvents,
  TelegramAdminEntry,
  TelegramSettings,
} from "../../api/types";
import { useSession } from "../../auth/session";
import { Button } from "../../ui/Button";
import { Card } from "../../ui/Card";
import { ErrorState } from "../../ui/ErrorState";
import { Section } from "../../ui/Section";
import { Skeleton } from "../../ui/Skeleton";
import { useToast } from "../../ui/Toaster";
import { settingsErrorText } from "../settings/accountView";
import { INPUT_CLASS, LABEL_CLASS } from "../settings/formStyles";

export const TELEGRAM_KEY = "telegram";

const EVENT_LABELS: { key: keyof NotifyEvents; label: string }[] = [
  { key: "approval", label: "Approval needed or expired" },
  { key: "escalated", label: "Escalated to a person" },
  { key: "resolved", label: "Resolved" },
  { key: "opened", label: "Every new incident" },
];

export function TelegramAdmin() {
  const { me } = useSession();
  if (me.role !== "admin") {
    return null;
  }
  return <TelegramSection />;
}

function TelegramSection() {
  const query = useQuery({ queryKey: [TELEGRAM_KEY], queryFn: getTelegram });
  return (
    <Section heading="Telegram">
      <p className="m-0 text-sm text-muted">
        Messages go straight to each admin when an incident needs a person.
        Create a bot with @BotFather, paste its token here and list the admins;
        everything else is managed inside the bot.
      </p>
      {query.isPending && <Skeleton lines={4} />}
      {query.isError && (
        <ErrorState
          title="Could not load the Telegram settings"
          message={settingsErrorText(query.error)}
          onRetry={() => void query.refetch()}
        />
      )}
      {query.isSuccess && (
        <div className="grid gap-3 lg:grid-cols-2">
          <TokenCard settings={query.data} />
          <SettingsCard
            key={JSON.stringify(query.data)}
            settings={query.data}
          />
        </div>
      )}
    </Section>
  );
}

function useStore() {
  const queryClient = useQueryClient();
  return (settings: TelegramSettings) =>
    queryClient.setQueryData([TELEGRAM_KEY], settings);
}

function TokenCard({ settings }: { settings: TelegramSettings }) {
  const toast = useToast();
  const store = useStore();
  const [token, setToken] = useState("");
  const [proxy, setProxy] = useState("");

  const tokenMutation = useMutation({
    mutationFn: (value: string | null) =>
      value === null ? removeTelegramToken() : setTelegramToken(value),
    onSuccess: (updated) => {
      store(updated);
      setToken("");
      toast.success(
        updated.token_last4 === null
          ? "Removed the bot token."
          : "Saved the bot token.",
      );
    },
  });
  const proxyMutation = useMutation({
    mutationFn: (value: string | null) => setTelegramProxy(value),
    onSuccess: (updated) => {
      store(updated);
      setProxy("");
      toast.success("Saved the Telegram proxy.");
    },
  });

  function saveToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    tokenMutation.mutate(token.trim());
  }

  function saveProxy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    proxyMutation.mutate(proxy.trim() === "" ? null : proxy.trim());
  }

  return (
    <Card title="Bot">
      <form onSubmit={saveToken} className="grid gap-3">
        <p className="m-0 text-sm">
          Token:{" "}
          <span className="font-medium">
            {settings.token_last4 === null
              ? "not set"
              : `…${settings.token_last4}`}
          </span>
        </p>
        <label className={LABEL_CLASS}>
          New bot token
          <input
            name="telegram-token"
            type="password"
            autoComplete="off"
            spellCheck={false}
            maxLength={100}
            value={token}
            onChange={(event) => setToken(event.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        {tokenMutation.isError && (
          <p role="alert" className="m-0 text-sm text-critical">
            {settingsErrorText(tokenMutation.error)}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            type="submit"
            size="sm"
            variant="primary"
            disabled={tokenMutation.isPending || token.trim() === ""}
          >
            Save token
          </Button>
          <Button
            size="sm"
            variant="danger"
            disabled={tokenMutation.isPending || settings.token_last4 === null}
            onClick={() => tokenMutation.mutate(null)}
          >
            Remove token
          </Button>
        </div>
      </form>
      <form
        onSubmit={saveProxy}
        className="mt-5 grid gap-3 border-t border-border pt-4"
      >
        <p className="m-0 text-sm">
          Proxy:{" "}
          <span className="font-medium">
            {settings.proxy_display ?? "none"}
          </span>
        </p>
        <label className={LABEL_CLASS}>
          Proxy URL (leave empty for none)
          <input
            name="telegram-proxy"
            type="text"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            placeholder="http://127.0.0.1:10950"
            maxLength={512}
            value={proxy}
            onChange={(event) => setProxy(event.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        {proxyMutation.isError && (
          <p role="alert" className="m-0 text-sm text-critical">
            {settingsErrorText(proxyMutation.error)}
          </p>
        )}
        <div>
          <Button type="submit" size="sm" disabled={proxyMutation.isPending}>
            Save proxy
          </Button>
        </div>
      </form>
    </Card>
  );
}

function adminStatus(admin: TelegramAdminEntry): string {
  if (!admin.linked) {
    return "has not written to the bot yet";
  }
  return admin.muted ? "muted in the bot" : "gets messages";
}

function adminName(admin: TelegramAdminEntry): string {
  return admin.username !== null && !admin.handle.startsWith("@")
    ? `${admin.handle} (@${admin.username})`
    : admin.handle;
}

function botSummary(settings: TelegramSettings): string {
  const chosen = EVENT_LABELS.filter((item) => settings.events[item.key]).map(
    (item) => item.label.toLowerCase(),
  );
  const when = chosen.length === 0 ? "nothing is chosen" : chosen.join(", ");
  return `Messages are ${settings.paused ? "paused" : "on"}. Sent when: ${when}.`;
}

function SettingsCard({ settings }: { settings: TelegramSettings }) {
  const toast = useToast();
  const store = useStore();
  const [admins, setAdmins] = useState<string[]>(
    settings.admins.map((admin) => admin.handle),
  );
  const [newAdmin, setNewAdmin] = useState("");
  const [panelUrl, setPanelUrl] = useState(settings.panel_url);
  const known = new Map(settings.admins.map((admin) => [admin.handle, admin]));

  const saveMutation = useMutation({
    mutationFn: () => saveTelegram({ panel_url: panelUrl.trim(), admins }),
    onSuccess: (updated) => {
      store(updated);
      toast.success("Saved the Telegram admins.");
    },
  });
  const testMutation = useMutation({ mutationFn: testTelegram });

  function addAdmin() {
    const handle = newAdmin.trim();
    if (handle !== "" && !admins.includes(handle)) {
      setAdmins([...admins, handle]);
    }
    setNewAdmin("");
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    saveMutation.mutate();
  }

  const canTest =
    settings.token_last4 !== null &&
    settings.admins.some((admin) => admin.linked);

  return (
    <Card title="Admins">
      <form onSubmit={submit} className="grid gap-3">
        <p className="m-0 text-sm text-muted">
          Admins get the messages and manage the bot from Telegram. Each one
          opens the bot and sends /start once; after that, /settings turns
          messages and event types on or off, and /add or /remove changes the
          admins.
        </p>
        <ul
          aria-label="Telegram admins"
          className="m-0 grid list-none gap-2 p-0"
        >
          {admins.length === 0 && (
            <li className="text-sm text-muted">No admins yet.</li>
          )}
          {admins.map((handle) => {
            const admin = known.get(handle);
            return (
              <li
                key={handle}
                className="flex flex-wrap items-center justify-between gap-2 text-sm"
              >
                <span>
                  <span className="font-medium">
                    {admin === undefined ? handle : adminName(admin)}
                  </span>{" "}
                  <span className="text-xs text-muted">
                    (
                    {admin === undefined ? "not saved yet" : adminStatus(admin)}
                    )
                  </span>
                </span>
                <Button
                  size="sm"
                  variant="danger"
                  aria-label={`Remove ${handle}`}
                  onClick={() =>
                    setAdmins(admins.filter((item) => item !== handle))
                  }
                >
                  Remove
                </Button>
              </li>
            );
          })}
        </ul>
        <div className="flex flex-wrap items-end gap-2">
          <label className={`${LABEL_CLASS} min-w-0 flex-1`}>
            Telegram user id or @username
            <input
              name="telegram-admin"
              type="text"
              autoComplete="off"
              spellCheck={false}
              placeholder="123456789 or @name"
              maxLength={40}
              value={newAdmin}
              onChange={(event) => setNewAdmin(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addAdmin();
                }
              }}
              className={INPUT_CLASS}
            />
          </label>
          <Button
            size="sm"
            disabled={newAdmin.trim() === ""}
            onClick={addAdmin}
          >
            Add
          </Button>
        </div>
        <label className={LABEL_CLASS}>
          Panel address for links
          <input
            name="telegram-panel-url"
            type="text"
            inputMode="url"
            autoComplete="off"
            placeholder="https://noc.example.com"
            maxLength={200}
            value={panelUrl}
            onChange={(event) => setPanelUrl(event.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <p className="m-0 text-sm">
          {botSummary(settings)}{" "}
          <span className="text-muted">
            Change this in the bot with /settings.
          </span>
        </p>
        {saveMutation.isError && (
          <p role="alert" className="m-0 text-sm text-critical">
            {settingsErrorText(saveMutation.error)}
          </p>
        )}
        {testMutation.isSuccess && (
          <p
            role="status"
            className={`m-0 text-sm ${testMutation.data.ok ? "text-ok" : "text-critical"}`}
          >
            {testMutation.data.ok
              ? `Test message ${testMutation.data.detail}.`
              : `Test failed: ${testMutation.data.detail}`}
          </p>
        )}
        {testMutation.isError && (
          <p role="alert" className="m-0 text-sm text-critical">
            {settingsErrorText(testMutation.error)}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            type="submit"
            size="sm"
            variant="primary"
            disabled={saveMutation.isPending}
          >
            Save
          </Button>
          <Button
            size="sm"
            disabled={testMutation.isPending || !canTest}
            onClick={() => testMutation.mutate()}
          >
            <Send aria-hidden="true" size={14} />
            Send test message
          </Button>
        </div>
      </form>
    </Card>
  );
}
