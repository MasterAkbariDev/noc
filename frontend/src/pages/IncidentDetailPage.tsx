import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { getIncident } from "../api/client";
import { useToken } from "../auth/token";
import { FindingsList } from "../components/FindingsList";
import { PolicyTable } from "../components/PolicyTable";
import { StatusBadge } from "../components/StatusBadge";
import { errorMessage, formatConfidence, formatTime } from "../components/format";
import { useLivePollInterval } from "../live/useEventStream";

export function IncidentDetailPage() {
  const { token } = useToken();
  const { id = "" } = useParams();
  const refetchInterval = useLivePollInterval();

  const query = useQuery({
    queryKey: ["incident", id, token],
    queryFn: () => getIncident(token, id),
    enabled: token !== "" && id !== "",
    refetchInterval,
  });

  if (token === "") {
    return <p className="muted">Enter the API token above to load this incident.</p>;
  }
  if (query.isPending) {
    return <p className="muted">Loading incident...</p>;
  }
  if (query.isError) {
    return (
      <section>
        <Link to="/incidents">Back to incidents</Link>
        <p role="alert" className="error">{errorMessage(query.error)}</p>
      </section>
    );
  }

  const incident = query.data;
  return (
    <article>
      <Link to="/incidents">Back to incidents</Link>
      <h1>{incident.title}</h1>
      <StatusBadge status={incident.status} />

      <section className="card">
        <h2>Summary</h2>
        <dl className="summary">
          <dt>Severity</dt>
          <dd>{incident.severity}</dd>
          <dt>Target</dt>
          <dd>{incident.target}</dd>
          <dt>Opened</dt>
          <dd>{formatTime(incident.opened_at)}</dd>
          <dt>Root cause</dt>
          <dd>{incident.root_cause_code ?? "-"}</dd>
          <dt>Confidence</dt>
          <dd>{formatConfidence(incident.confidence)}</dd>
          <dt>Escalation reason</dt>
          <dd>{incident.escalation_reason ?? "-"}</dd>
          <dt>Trace</dt>
          <dd><code>{incident.trace_id}</code></dd>
        </dl>
      </section>

      <section>
        <h2>Findings</h2>
        <FindingsList findings={incident.findings} />
      </section>

      <section>
        <h2>Policy decisions</h2>
        <PolicyTable actions={incident.actions} />
      </section>

      <section>
        <h2>Report</h2>
        {incident.report_markdown === null ? (
          <p className="muted">Report not ready yet.</p>
        ) : (
          <pre className="report">{incident.report_markdown}</pre>
        )}
      </section>
    </article>
  );
}
