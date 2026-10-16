import type { UseQueryResult } from "@tanstack/react-query";
import { Server } from "lucide-react";
import type { IncidentSummary, ServerDetail, ServiceLive, TargetResource } from "../../api/types";
import { formatBytes } from "../../lib/format";
import { Badge } from "../../ui/Badge";
import { Sparkline } from "../../ui/charts";
import { Disclosure } from "../../ui/Disclosure";
import { type Column, DataTable } from "../../ui/DataTable";
import { EmptyState } from "../../ui/EmptyState";
import { ErrorState } from "../../ui/ErrorState";
import { IncidentStatusBadge } from "../../ui/IncidentStatusBadge";
import { DescriptionList, List, ListItem } from "../../ui/List";
import { RelativeTime } from "../../ui/RelativeTime";
import { Section } from "../../ui/Section";
import { SeverityBadge } from "../../ui/SeverityBadge";
import { Skeleton } from "../../ui/Skeleton";
import { lastValue } from "../live/range";
import { LivePanel, useServiceMemory } from "./LivePanel";
import { MetricBars } from "./MetricBar";
import { errorText, isNotFound, NOT_FOUND_MESSAGE, serviceView } from "./serverView";
import { IncidentLink } from "../incident/IncidentLink";

function TimeOrNever({ iso }: { iso: string | null }) {
  return iso === null ? <span className="text-muted">never</span> : <RelativeTime iso={iso} />;
}

function ServerFacts({ server }: { server: ServerDetail }) {
  return (
    <DescriptionList
      items={[
        { key: "scrape", term: "Last scrape", detail: <TimeOrNever iso={server.last_scrape_at} /> },
        { key: "inventory", term: "Last inventory", detail: <TimeOrNever iso={server.last_inventory_at} /> },
      ]}
    />
  );
}

function memoryText(service: ServiceLive | undefined): string | null {
  const used = service === undefined ? null : lastValue(service.memory_bytes);
  if (used === null) {
    return null;
  }
  const limit = service?.memory_limit_bytes ?? null;
  return limit === null ? `uses ${formatBytes(used)} of memory` : `uses ${formatBytes(used)} of its ${formatBytes(limit)} memory limit`;
}

function ServiceList({ server }: { server: ServerDetail }) {
  const live = useServiceMemory(server.id);
  if (server.services.length === 0) {
    return <p className="m-0 text-sm text-muted">No services are inventoried on this server.</p>;
  }
  return (
    <List variant="divided">
      {server.services.map((service) => {
        const view = serviceView(service.up);
        const memory = live.get(service.resource_id);
        const usage = memoryText(memory);
        const points = memory?.memory_bytes ?? [];
        return (
          <ListItem key={service.resource_id} className="flex flex-wrap items-center justify-between gap-3">
            <span className="grid min-w-0 gap-0.5">
              <span className="font-medium break-words">{service.name}</span>
              {usage !== null && <span className="text-sm text-muted">{usage}</span>}
            </span>
            <span className="flex items-center gap-3">
              {points.length > 1 && <Sparkline values={points.map(([, value]) => value)} color="var(--ui-accent)" />}
              <Badge tone={view.tone}>{view.label}</Badge>
            </span>
          </ListItem>
        );
      })}
    </List>
  );
}

function ResourceList({ resources }: { resources: TargetResource[] }) {
  if (resources.length === 0) {
    return <p className="m-0 text-sm text-muted">No resources inventoried yet.</p>;
  }
  return (
    <List gap="sm" className="text-sm">
      {resources.map((resource) => (
        <ListItem key={resource.resource_id} className="flex flex-wrap gap-2">
          <span className="text-muted">{resource.kind}</span>
          <span className="min-w-0 break-words">{resource.name}</span>
        </ListItem>
      ))}
    </List>
  );
}

const INCIDENT_COLUMNS: Column<IncidentSummary>[] = [
  {
    key: "title",
    header: "Incident",
    cell: (incident) => (
      <IncidentLink id={incident.id} className="font-medium underline-offset-4 hover:underline">
        {incident.title}
      </IncidentLink>
    ),
  },
  { key: "status", header: "Status", cell: (incident) => <IncidentStatusBadge status={incident.status} /> },
  { key: "severity", header: "Severity", cell: (incident) => <SeverityBadge severity={incident.severity} /> },
  { key: "opened", header: "Opened", cell: (incident) => <RelativeTime iso={incident.opened_at} /> },
];

function ServerContent({ server }: { server: ServerDetail }) {
  return (
    <div className="grid gap-2">
      <Section heading="Right now">
        <MetricBars metrics={server.metrics} />
      </Section>
      <LivePanel serverId={server.id} />
      <Section heading="Services">
        <ServiceList server={server} />
      </Section>
      <Section heading="Recent incidents">
        <DataTable
          label="Recent incidents"
          columns={INCIDENT_COLUMNS}
          rows={server.recent_incidents}
          rowKey={(incident) => incident.id}
          empty="No incidents have been recorded for this server."
        />
      </Section>
      <Disclosure summary="Technical details" hint="Scrape and inventory times, managed resources">
        <div className="grid gap-6">
          <ServerFacts server={server} />
          <ResourceList resources={server.resources} />
        </div>
      </Disclosure>
    </div>
  );
}

export function ServerBody({ query }: { query: UseQueryResult<ServerDetail, Error> }) {
  if (query.isPending) {
    return <Skeleton lines={6} />;
  }
  if (query.isError) {
    if (isNotFound(query.error)) {
      return <EmptyState icon={Server} title="Server not found" text={NOT_FOUND_MESSAGE} />;
    }
    return (
      <ErrorState
        title="Could not load this server"
        message={errorText(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  return <ServerContent server={query.data} />;
}
