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
import {
  Button,
  Card,
  ErrorState,
  Field,
  Form,
  FormActions,
  FormMessage,
  List,
  ListItem,
  Section,
  Skeleton,
  TextInput,
  useToast,
} from "../../ui";
import { settingsErrorText } from "../settings/accountView";

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
      <Form onSubmit={saveToken}>
        <p className="m-0 text-sm">
          Token:{" "}
          <span className="font-medium">
            {settings.token_last4 === null
              ? "not set"
              : `…${settings.token_last4}`}
          </span>
        </p>
        <Field label="New bot token">
          <TextInput
            name="telegram-token"
            type="password"
            autoComplete="off"
            spellCheck={false}
            maxLength={100}
            value={token}
            onChange={(event) => setToken(event.target.value)}
          />
        </Field>
        {tokenMutation.isError && <FormMessage>{settingsErrorText(tokenMutation.error)}</FormMessage>}
        <FormActions>
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
        </FormActions>
      </Form>
      <Form onSubmit={saveProxy} className="mt-5 border-t border-border pt-4">
        <p className="m-0 text-sm">
          Proxy:{" "}
          <span className="font-medium">
            {settings.proxy_display ?? "none"}
          </span>
        </p>
        <Field label="Proxy URL (leave empty for none)">
          <TextInput
            name="telegram-proxy"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            placeholder="http://127.0.0.1:10950"
            maxLength={512}
            value={proxy}
            onChange={(event) => setProxy(event.target.value)}
          />
        </Field>
        {proxyMutation.isError && <FormMessage>{settingsErrorText(proxyMutation.error)}</FormMessage>}
        <FormActions>
          <Button type="submit" size="sm" disabled={proxyMutation.isPending}>
            Save proxy
          </Button>
        </FormActions>
      </Form>
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
      <Form onSubmit={submit}>
        <p className="m-0 text-sm text-muted">
          Admins get the messages and manage the bot from Telegram. Each one
          opens the bot and sends /start once; after that, /settings turns
          messages and event types on or off, and /add or /remove changes the
          admins.
        </p>
        <List label="Telegram admins" variant="divided">
          {admins.length === 0 && <ListItem className="text-sm text-muted">No admins yet.</ListItem>}
          {admins.map((handle) => {
            const admin = known.get(handle);
            return (
              <ListItem key={handle} className="flex flex-wrap items-center justify-between gap-2 text-sm">
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
              </ListItem>
            );
          })}
        </List>
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Telegram user id or @username" className="flex-1">
            <TextInput
              name="telegram-admin"
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
            />
          </Field>
          <Button
            size="sm"
            disabled={newAdmin.trim() === ""}
            onClick={addAdmin}
          >
            Add
          </Button>
        </div>
        <Field label="Panel address for links">
          <TextInput
            name="telegram-panel-url"
            inputMode="url"
            autoComplete="off"
            placeholder="https://noc.example.com"
            maxLength={200}
            value={panelUrl}
            onChange={(event) => setPanelUrl(event.target.value)}
          />
        </Field>
        <p className="m-0 text-sm">
          {botSummary(settings)}{" "}
          <span className="text-muted">
            Change this in the bot with /settings.
          </span>
        </p>
        {saveMutation.isError && <FormMessage>{settingsErrorText(saveMutation.error)}</FormMessage>}
        {testMutation.isSuccess && (
          <FormMessage tone={testMutation.data.ok ? "ok" : "critical"}>
            {testMutation.data.ok
              ? `Test message ${testMutation.data.detail}.`
              : `Test failed: ${testMutation.data.detail}`}
          </FormMessage>
        )}
        {testMutation.isError && <FormMessage>{settingsErrorText(testMutation.error)}</FormMessage>}
        <FormActions>
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
        </FormActions>
      </Form>
    </Card>
  );
}
