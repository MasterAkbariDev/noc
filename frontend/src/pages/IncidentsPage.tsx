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
  const refetchInterval = useLivePollInterval();

  const query = useQuery({
    queryKey: ["incidents", status, token],
    queryFn: () => listIncidents(token, status || undefined),
    enabled: token !== "",
    refetchInterval,
  });

  function changeStatus(next: string) {
    setParams(next ? { status: next } : {});
  }

  return (
    <section>
      <div className="page-head">
        <h1>Incidents</h1>
        <label>
          Status{" "}
          <select value={status} onChange={(event) => changeStatus(event.target.value)}>
            <option value="">All</option>
            {INCIDENT_STATUSES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
      </div>
      {token === "" && <p className="muted">Enter the API token above to load incidents.</p>}
      {token !== "" && query.isPending && <p className="muted">Loading incidents...</p>}
      {query.isError && <p role="alert" className="error">{errorMessage(query.error)}</p>}
      {query.data && <IncidentTable incidents={query.data} />}
    </section>
  );
}
