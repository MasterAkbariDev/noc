import { Clock, CircleCheck, CircleDashed, CircleX, type LucideIcon } from "lucide-react";
import type { LlmKeyView, LlmModelUsage, LlmStatus } from "../../api/types";
import { Badge, DataTable, List, ListItem, RelativeTime, Term, type Column } from "../../ui";
import { keyStateView, llmModeView, usagePercent, usageText } from "./view";

const REPLAY_NOTE =
  "Replay mode: answers come from a recorded file, not from the providers. The usage and key state below do not describe live traffic.";

const STATE_ICONS = new Map<string, LucideIcon>([
  ["ok", CircleCheck],
  ["cooling", Clock],
  ["rejected", CircleX],
  ["unused", CircleDashed],
]);

function KeyState({ keyView }: { keyView: LlmKeyView }) {
  const view = keyStateView(keyView.state);
  const icon = STATE_ICONS.get(keyView.state) ?? CircleDashed;
  return (
    <div className="grid justify-items-start gap-1">
      <Badge tone={view.tone} icon={icon}>
        {view.label}
      </Badge>
      {keyView.cooling_until !== null && (
        <span className="text-xs text-muted">
          Until <RelativeTime iso={keyView.cooling_until} />
        </span>
      )}
    </div>
  );
}

function UsageBar({ model }: { model: LlmModelUsage }) {
  const percent = usagePercent(model.used_today, model.daily_limit);
  return (
    <ListItem className="grid gap-1">
      <span className="text-sm">
        <span className="font-medium">{model.tier}</span> <code className="break-all text-xs">{model.model}</code>
      </span>
      <span className="text-xs text-muted">{usageText(model.used_today, model.daily_limit)}</span>
      <span aria-hidden="true" className="block h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <span className="block h-full rounded-full bg-info" style={{ width: `${percent}%` }} />
      </span>
    </ListItem>
  );
}

function LastEvents({ keyView }: { keyView: LlmKeyView }) {
  return (
    <div className="grid gap-1 text-sm">
      {keyView.last_error !== null ? (
        <span className="grid gap-1">
          <code className="break-all text-xs">{keyView.last_error}</code>
          {keyView.last_error_at !== null && (
            <span className="text-xs text-muted">
              <RelativeTime iso={keyView.last_error_at} />
            </span>
          )}
        </span>
      ) : (
        <span className="text-muted">No error recorded</span>
      )}
      <span className="text-xs text-muted">
        Last success:{" "}
        {keyView.last_success_at !== null ? <RelativeTime iso={keyView.last_success_at} /> : "none yet"}
      </span>
    </div>
  );
}

const KEY_COLUMNS: Column<LlmKeyView>[] = [
  {
    key: "key",
    header: "Key",
    cell: (keyView) => (
      <div className="grid gap-1">
        <code className="break-all text-xs">{keyView.label}</code>
        <span className="text-muted">{keyView.provider}</span>
      </div>
    ),
    className: "min-w-[9rem]",
  },
  {
    key: "state",
    header: "State",
    cell: (keyView) => <KeyState keyView={keyView} />,
    className: "whitespace-nowrap",
  },
  {
    key: "models",
    header: "Models today",
    cell: (keyView) => (
      <List className="min-w-[12rem]">
        {keyView.models.map((model) => (
          <UsageBar key={`${model.tier}-${model.model}`} model={model} />
        ))}
      </List>
    ),
    className: "min-w-[12rem]",
  },
  {
    key: "events",
    header: "Errors and successes",
    cell: (keyView) => <LastEvents keyView={keyView} />,
    className: "min-w-[12rem]",
  },
];

export function LlmPanel({ status }: { status: LlmStatus }) {
  const mode = llmModeView(status.mode);
  return (
    <div className="grid gap-3">
      <p className="m-0 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">Mode</span>
        <Badge tone={mode.tone}>
          <Term technical={status.mode}>{mode.label}</Term>
        </Badge>
      </p>
      {status.mode === "replay" && (
        <p role="note" className="m-0 rounded-control border border-border bg-surface-2 p-3 text-sm">
          {REPLAY_NOTE}
        </p>
      )}
      <DataTable
        label="LLM keys"
        columns={KEY_COLUMNS}
        rows={status.keys}
        rowKey={(keyView) => keyView.label}
        empty="No LLM keys are configured."
      />
    </div>
  );
}
