import type { UseQueryResult } from "@tanstack/react-query";
import { Link } from "react-router";
import { Server } from "lucide-react";
import type { IncidentSummary, ServerDetail, TargetResource } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { type Column, DataTable } from "../../ui/DataTable";
import { EmptyState } from "../../ui/EmptyState";
import { ErrorState } from "../../ui/ErrorState";
import { IncidentStatusBadge } from "../../ui/IncidentStatusBadge";
import { RelativeTime } from "../../ui/RelativeTime";
import { Section } from "../../ui/Section";
import { SeverityBadge } from "../../ui/SeverityBadge";
import { Skeleton } from "../../ui/Skeleton";
import { MetricBars } from "./MetricBar";
import { errorText, isNotFound, NOT_FOUND_MESSAGE, serviceView } from "./serverView";

function TimeOrNever({ iso }: { iso: string | null }) {
  return iso === null ? <span className="text-muted">never</span> : <RelativeTime iso={iso} />;
}

function ServerFacts({ server }: { server: ServerDetail }) {
  return (
    <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
      <dt className="text-muted">Last scrape</dt>
      <dd className="m-0">
        <TimeOrNever iso={server.last_scrape_at} />
      </dd>
      <dt className="text-muted">Last inventory</dt>
      <dd className="m-0">
        <TimeOrNever iso={server.last_inventory_at} />
      </dd>
    </dl>
  );
}

function ServiceList({ server }: { server: ServerDetail }) {
  if (server.services.length === 0) {
    return <p className="m-0 text-sm text-muted">No services are inventoried on this server.</p>;
  }
  return (
    <ul className="m-0 grid list-none gap-2 p-0">
      {server.services.map((service) => {
        const view = serviceView(service.up);
        return (
          <li key={service.resource_id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="min-w-0 break-words">{service.name}</span>
            <Badge tone={view.tone}>{view.label}</Badge>
          </li>
        );
      })}
    </ul>
  );
}

function ResourceList({ resources }: { resources: TargetResource[] }) {
  if (resources.length === 0) {
    return <p className="m-0 text-sm text-muted">No resources inventoried yet.</p>;
  }
  return (
    <ul className="m-0 grid list-none gap-2 p-0 text-sm">
      {resources.map((resource) => (
        <li key={resource.resource_id} className="flex flex-wrap gap-2">
          <span className="text-muted">{resource.kind}</span>
          <span className="min-w-0 break-words">{resource.name}</span>
        </li>
      ))}
    </ul>
  );
}

const INCIDENT_COLUMNS: Column<IncidentSummary>[] = [
  {
    key: "title",
    header: "Incident",
    cell: (incident) => (
      <Link to={`/incidents/${encodeURIComponent(incident.id)}`} className="font-medium underline-offset-4 hover:underline">
        {incident.title}
      </Link>
    ),
  },
  { key: "status", header: "Status", cell: (incident) => <IncidentStatusBadge status={incident.status} /> },
  { key: "severity", header: "Severity", cell: (incident) => <SeverityBadge severity={incident.severity} /> },
  { key: "opened", header: "Opened", cell: (incident) => <RelativeTime iso={incident.opened_at} /> },
];

function ServerContent({ server }: { server: ServerDetail }) {
  return (
    <div className="grid gap-8">
      <Section heading="Status">
        <ServerFacts server={server} />
      </Section>
      <Section heading="Metrics">
        <MetricBars metrics={server.metrics} />
      </Section>
      <Section heading="Services">
        <ServiceList server={server} />
      </Section>
      <Section heading="Resources">
        <ResourceList resources={server.resources} />
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
