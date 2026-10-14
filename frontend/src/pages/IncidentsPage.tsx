import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import type { IncidentSummary } from "../api/types";
import { IncidentFilters } from "../features/incidents/IncidentFilters";
import { IncidentRows } from "../features/incidents/IncidentRows";
import { listAllIncidents } from "../features/incidents/api";
import {
  FILTER_EMPTY_TEXT,
  matchesFilter,
  matchesSearch,
  matchesSeverity,
  parseFilter,
} from "../features/incidents/filters";
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
  const search = params.get("q") ?? "";

  const query = useQuery({
    queryKey: ["incidents", "list"],
    queryFn: listAllIncidents,
    refetchInterval,
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
  const inFilter = incidents.filter((incident) => matchesFilter(incident, filter));
  const visible = inFilter.filter(
    (incident) => matchesSeverity(incident, severity) && matchesSearch(incident, search),
  );
  const emptyText = inFilter.length === 0 ? FILTER_EMPTY_TEXT[filter] : "No incidents match these filters.";

  return (
    <>
      <PageHeader title="Incidents" />
      <IncidentFilters
        filter={filter}
        severity={severity}
        severities={severityOptions(incidents, severity)}
        search={search}
        onFilterChange={(value) => setParam("filter", value, false)}
        onSeverityChange={(value) => setParam("severity", value, false)}
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
