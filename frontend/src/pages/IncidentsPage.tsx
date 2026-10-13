import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { listIncidents } from "../api/client";
import { INCIDENT_STATUSES } from "../api/types";
import { useToken } from "../auth/token";
import { IncidentTable } from "../components/IncidentTable";
import { errorMessage } from "../components/format";
import { useLivePollInterval } from "../live/useEventStream";

export function IncidentsPage() {
  const { token } = useToken();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const severity = params.get("severity") ?? "";
  const refetchInterval = useLivePollInterval();

  const query = useQuery({
    queryKey: ["incidents", status, token],
    queryFn: () => listIncidents(token, status || undefined),
    enabled: token !== "",
    refetchInterval,
  });

  function changeFilter(key: "status" | "severity", value: string) {
    const next = new URLSearchParams(params);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setParams(next);
  }

  const incidents = query.data ?? [];
  const visible = severity ? incidents.filter((incident) => incident.severity === severity) : incidents;
  const severities = [
    ...new Set([...incidents.map((incident) => incident.severity), ...(severity ? [severity] : [])]),
  ].sort();

  return (
    <section>
      <div className="page-head">
        <h1>Incidents</h1>
        <div className="filters">
          <label>
            Status{" "}
            <select value={status} onChange={(event) => changeFilter("status", event.target.value)}>
              <option value="">All</option>
              {INCIDENT_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            Severity{" "}
            <select value={severity} onChange={(event) => changeFilter("severity", event.target.value)}>
              <option value="">All</option>
              {severities.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      {token === "" && <p className="muted">Enter the API token above to load incidents.</p>}
      {token !== "" && query.isPending && <p className="muted">Loading incidents...</p>}
      {query.isError && <p role="alert" className="error">{errorMessage(query.error)}</p>}
      {query.data && <IncidentTable incidents={visible} />}
    </section>
  );
}
