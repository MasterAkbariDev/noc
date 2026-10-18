import type { ReactNode } from "react";
import { Link } from "react-router";
import type { ServerStatus, ServerSummary } from "../../api/types";
import { cx } from "../../lib/cx";
import { Card } from "../../ui/Card";
import { AutomationLevel, EnvironmentBadge, HaltedBadge, OpenIncidents, ServerStatusDot } from "./ServerParts";
import { MetricBars } from "./MetricBar";
import { ServerAdmin } from "./ServerAdmin";
import { headlineWithoutIncidents } from "./serverView";

const STATUS_BORDERS: Record<ServerStatus, string> = {
  up: "border-t-ok",
  down: "border-t-critical",
  unknown: "border-t-unknown",
};

type ServerCardProps = {
  server: ServerSummary;
  readOnly?: boolean;
  // Name of the NOC this server came from, for servers shown from another node.
  node?: string;
  // Controls that belong to a remote server, shown at the bottom of its card.
  footer?: ReactNode;
};

export function ServerCard({ server, readOnly = false, node, footer }: ServerCardProps) {
  const headline = headlineWithoutIncidents(server.headline, server.open_incidents);
  return (
    <Card className={cx("flex h-full flex-col gap-3 rounded-card border-t-4 shadow-sm", STATUS_BORDERS[server.status])}>
      <div className="flex flex-wrap items-center gap-2">
        <ServerStatusDot status={server.status} />
        <EnvironmentBadge environment={server.environment} />
        {server.tag && <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent">{server.tag}</span>}
        {node && <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted">From {node}</span>}
        {server.halted && <HaltedBadge />}
      </div>
      <div className="grid gap-0.5">
        <h2 className="m-0 text-lg font-semibold break-words">
          {readOnly ? (
            server.label ?? server.name
          ) : (
            <Link to={`/servers/${encodeURIComponent(server.id)}`} className="underline-offset-4 hover:text-accent hover:underline">
              {server.label ?? server.name}
            </Link>
          )}
        </h2>
        {server.label && <p className="m-0 text-xs text-muted break-all">{server.name}</p>}
      </div>
      {headline !== "" && <p className="m-0 text-sm">{headline}</p>}
      <MetricBars metrics={server.metrics} />
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 text-sm">
        <AutomationLevel level={server.automation_level} label={server.automation_label} />
        <OpenIncidents count={server.open_incidents} worstSeverity={server.worst_severity} />
      </div>
      {!readOnly && <ServerAdmin server={server} />}
      {footer}
    </Card>
  );
}
