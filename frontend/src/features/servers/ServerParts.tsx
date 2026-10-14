import { OctagonAlert } from "lucide-react";
import type { ServerStatus, ServerSummary } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { SeverityBadge } from "../../ui/SeverityBadge";
import { StatusDot } from "../../ui/StatusDot";
import { Term } from "../../ui/Term";
import { environmentTone, openIncidentsText, serverStatusView } from "./serverView";

export function ServerStatusDot({ status }: { status: ServerStatus }) {
  const view = serverStatusView(status);
  return (
    <span className="font-semibold">
      <StatusDot tone={view.tone} label={view.label} showLabel />
    </span>
  );
}

export function ServerStatusLine({ server }: { server: ServerSummary }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
      <ServerStatusDot status={server.status} />
      <EnvironmentBadge environment={server.environment} />
      {server.halted && <HaltedBadge />}
      <span>{server.headline}</span>
    </span>
  );
}

export function EnvironmentBadge({ environment }: { environment: string }) {
  return <Badge tone={environmentTone(environment)}>{environment}</Badge>;
}

export function HaltedBadge() {
  return (
    <Badge tone="critical" icon={OctagonAlert}>
      Halted
    </Badge>
  );
}

export function AutomationLevel({ level, label }: { level: string; label: string }) {
  return (
    <span>
      Automation: <Term technical={level}>{label}</Term>
    </span>
  );
}

export function OpenIncidents({ count, worstSeverity }: { count: number; worstSeverity: string | null }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <span>{openIncidentsText(count)}</span>
      {worstSeverity !== null && <SeverityBadge severity={worstSeverity} />}
    </span>
  );
}
