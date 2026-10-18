import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import type { IncidentSummary } from "../api/types";
import { useServersQuery } from "../features/servers/queries";
import { IncidentFilters } from "../features/incidents/IncidentFilters";
import { IncidentRows } from "../features/incidents/IncidentRows";
import { listIncidentRows } from "../features/incidents/api";
import { FILTER_EMPTY_TEXT, matchesSeverity, parseFilter, statusesFor } from "../features/incidents/filters";
import { remoteIncidents, useFollowedPeers } from "../features/nodes/RemoteServers";
import { SEARCH_DEBOUNCE_MS, useDebouncedValue } from "../features/incidents/useDebouncedValue";
import { useLivePollInterval } from "../live/useEventStream";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { ErrorState, PageHeader, Skeleton } from "../ui";

function severityOptions(incidents: IncidentSummary[], selected: string): string[] {
  const values = new Set(incidents.map((incident) => incident.severity));
  if (selected !== "") {
    values.add(selected);
  }
  return [...values].sort();
}

function failureText(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail;
  }
  return "Could not reach the NOC. Try again.";
}

export function IncidentsPage() {
  useDocumentTitle("Incidents");
  const [params, setParams] = useSearchParams();
  const refetchInterval = useLivePollInterval();
  const filter = parseFilter(params.get("filter"));
  const severity = params.get("severity") ?? "";
  const server = params.get("server") ?? "";
  const search = params.get("q") ?? "";
  const debouncedSearch = useDebouncedValue(search, SEARCH_DEBOUNCE_MS);

  const query = useQuery({
    queryKey: ["incidents", "list", filter, debouncedSearch],
    queryFn: () => listIncidentRows(filter, debouncedSearch),
    refetchInterval,
    placeholderData: keepPreviousData,
  });

  function setParam(key: string, value: string, replace: boolean) {
    const next = new URLSearchParams(params);
    if (value === "") {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    setParams(next, { replace });
  }

  const incidents = query.data ?? [];
  const followed = useFollowedPeers();
  const serversQuery = useServersQuery();
  const needle = debouncedSearch.trim().toLowerCase();
  const remote = remoteIncidents(followed).filter(
    (incident) =>
      statusesFor(filter).includes(incident.status) &&
      (needle === "" || incident.title.toLowerCase().includes(needle) || incident.target.toLowerCase().includes(needle)),
  );
  const all = [...incidents, ...remote];
  const visible = all.filter(
    (incident) => matchesSeverity(incident, severity) && (server === "" || incident.target === server),
  );
  // Every known server belongs in the filter, even one without incidents yet.
  const localServers = serversQuery.data ?? [];
  const remoteServers = followed.flatMap((peer) => peer.last_status?.servers ?? []);
  const servers = [
    ...new Set([
      ...localServers.map((server) => server.name),
      ...remoteServers.map((server) => server.name),
      ...all.map((incident) => incident.target),
    ]),
  ].sort();
  const nothingNarrowsTheList = debouncedSearch.trim() === "" && severity === "" && server === "";
  const emptyText =
    incidents.length === 0 && nothingNarrowsTheList
      ? FILTER_EMPTY_TEXT[filter]
      : "No incidents match these filters.";

  return (
    <>
      <PageHeader title="Incidents" status="Every incident the NOC opened, newest first." />
      <IncidentFilters
        filter={filter}
        severity={severity}
        severities={severityOptions(incidents, severity)}
        server={server}
        servers={servers}
        search={search}
        onFilterChange={(value) => setParam("filter", value, false)}
        onSeverityChange={(value) => setParam("severity", value, false)}
        onServerChange={(value) => setParam("server", value, false)}
        onSearchChange={(value) => setParam("q", value, true)}
      />
      {query.isPending && <Skeleton lines={5} />}
      {query.isError && (
        <ErrorState
          title="Incidents did not load"
          message={failureText(query.error)}
          onRetry={() => void query.refetch()}
        />
      )}
      {query.isSuccess && <IncidentRows incidents={visible} emptyText={emptyText} />}
    </>
  );
}
