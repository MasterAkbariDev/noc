import { useQuery } from "@tanstack/react-query";
import { getTargets } from "../api/client";
import { useToken } from "../auth/token";
import { errorMessage } from "../components/format";
import { TargetCard } from "../components/TargetCard";

export const TARGETS_POLL_MS = 30000;

export function TargetsPage() {
  const { token } = useToken();

  const query = useQuery({
    queryKey: ["targets"],
    queryFn: () => getTargets(token),
    enabled: token !== "",
    refetchInterval: TARGETS_POLL_MS,
  });

  return (
    <section>
      <div className="page-head">
        <h1>Targets</h1>
      </div>
      {token === "" && <p className="muted">Enter the API token above to load targets.</p>}
      {token !== "" && query.isPending && <p className="muted">Loading targets...</p>}
      {token !== "" && query.isError && <p role="alert" className="error">{errorMessage(query.error)}</p>}
      {token !== "" && query.data && query.data.length === 0 && <p className="muted">No targets are registered.</p>}
      {token !== "" && query.data && query.data.length > 0 && (
        <div className="target-grid">
          {query.data.map((target) => (
            <TargetCard key={target.id} target={target} />
          ))}
        </div>
      )}
    </section>
  );
}
