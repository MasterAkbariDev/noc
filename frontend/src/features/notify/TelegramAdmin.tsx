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
import type { NotifyEvents, TelegramSettings } from "../../api/types";
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

const EVENT_LABELS: { key: keyof NotifyEvents; label: string; hint: string }[] = [
  { key: "approval", label: "Approval needed or expired", hint: "An action waits for a person" },
  { key: "escalated", label: "Escalated", hint: "The NOC hands the incident to a person" },
  { key: "resolved", label: "Resolved", hint: "Fixed, or recovered on its own" },
  { key: "opened", label: "New incident", hint: "Every new incident (can be noisy)" },
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
        Messages go to one chat or channel when an incident needs a person. Create a bot with @BotFather, add it to the
        chat, then paste its token and the chat id here.
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
          <SettingsCard key={JSON.stringify(query.data)} settings={query.data} />
        </div>
      )}
    </Section>
  );
}

function useStore() {
  const queryClient = useQueryClient();
  return (settings: TelegramSettings) => queryClient.setQueryData([TELEGRAM_KEY], settings);
}

function TokenCard({ settings }: { settings: TelegramSettings }) {
  const toast = useToast();
  const store = useStore();
  const [token, setToken] = useState("");
  const [proxy, setProxy] = useState("");

  const tokenMutation = useMutation({
    mutationFn: (value: string | null) => (value === null ? removeTelegramToken() : setTelegramToken(value)),
    onSuccess: (updated) => {
      store(updated);
      setToken("");
      toast.success(updated.token_last4 === null ? "Removed the bot token." : "Saved the bot token.");
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
            {settings.token_last4 === null ? "not set" : `…${settings.token_last4}`}
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
          <Button type="submit" size="sm" variant="primary" disabled={tokenMutation.isPending || token.trim() === ""}>
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
      <form onSubmit={saveProxy} className="mt-5 grid gap-3 border-t border-border pt-4">
        <p className="m-0 text-sm">
          Proxy: <span className="font-medium">{settings.proxy_display ?? "none"}</span>
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

function SettingsCard({ settings }: { settings: TelegramSettings }) {
  const toast = useToast();
  const store = useStore();
  const [enabled, setEnabled] = useState(settings.enabled);
  const [chatId, setChatId] = useState(settings.chat_id);
  const [panelUrl, setPanelUrl] = useState(settings.panel_url);
  const [events, setEvents] = useState<NotifyEvents>(settings.events);

  const saveMutation = useMutation({
    mutationFn: () => saveTelegram({ enabled, chat_id: chatId.trim(), panel_url: panelUrl.trim(), events }),
    onSuccess: (updated) => {
      store(updated);
      toast.success(updated.enabled ? "Telegram notifications are on." : "Saved. Telegram notifications are off.");
    },
  });
  const testMutation = useMutation({ mutationFn: testTelegram });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    saveMutation.mutate();
  }

  return (
    <Card title="Where and when">
      <form onSubmit={submit} className="grid gap-3">
        <label className="flex items-center gap-2 text-sm font-medium">
          <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
          Send notifications
        </label>
        <label className={LABEL_CLASS}>
          Chat id
          <input
            name="telegram-chat"
            type="text"
            autoComplete="off"
            spellCheck={false}
            placeholder="-1001234567890 or @channel"
            maxLength={40}
            value={chatId}
            onChange={(event) => setChatId(event.target.value)}
            className={INPUT_CLASS}
          />
        </label>
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
        <fieldset className="m-0 grid gap-2 border-0 p-0">
          <legend className="mb-1 text-sm font-medium">Send a message when</legend>
          {EVENT_LABELS.map((item) => (
            <label key={item.key} className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={events[item.key]}
                onChange={(event) => setEvents({ ...events, [item.key]: event.target.checked })}
              />
              <span>
                {item.label} <span className="text-xs text-muted">({item.hint})</span>
              </span>
            </label>
          ))}
        </fieldset>
        {saveMutation.isError && (
          <p role="alert" className="m-0 text-sm text-critical">
            {settingsErrorText(saveMutation.error)}
          </p>
        )}
        {testMutation.isSuccess && (
          <p role="status" className={`m-0 text-sm ${testMutation.data.ok ? "text-ok" : "text-critical"}`}>
            {testMutation.data.ok ? "Test message sent." : `Test failed: ${testMutation.data.detail}`}
          </p>
        )}
        {testMutation.isError && (
          <p role="alert" className="m-0 text-sm text-critical">
            {settingsErrorText(testMutation.error)}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" size="sm" variant="primary" disabled={saveMutation.isPending}>
            Save
          </Button>
          <Button
            size="sm"
            disabled={testMutation.isPending || settings.token_last4 === null || settings.chat_id === ""}
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
