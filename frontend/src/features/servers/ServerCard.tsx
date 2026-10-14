import { Link } from "react-router";
import type { ServerSummary } from "../../api/types";
import { Card } from "../../ui/Card";
import { AutomationLevel, EnvironmentBadge, HaltedBadge, OpenIncidents, ServerStatusDot } from "./ServerParts";
import { MetricBars } from "./MetricBar";
import { headlineWithoutIncidents } from "./serverView";

export function ServerCard({ server }: { server: ServerSummary }) {
  const headline = headlineWithoutIncidents(server.headline, server.open_incidents);
  return (
    <Card className="flex h-full flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <ServerStatusDot status={server.status} />
        <EnvironmentBadge environment={server.environment} />
        {server.halted && <HaltedBadge />}
      </div>
      <h2 className="m-0 text-lg font-semibold break-words">
        <Link to={`/servers/${encodeURIComponent(server.id)}`} className="underline-offset-4 hover:underline">
          {server.name}
        </Link>
      </h2>
      {headline !== "" && <p className="m-0 text-sm">{headline}</p>}
      <MetricBars metrics={server.metrics} />
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 text-sm">
        <AutomationLevel level={server.automation_level} label={server.automation_label} />
        <OpenIncidents count={server.open_incidents} worstSeverity={server.worst_severity} />
      </div>
    </Card>
  );
}
