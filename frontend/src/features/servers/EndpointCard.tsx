import type { EndpointView } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { Card } from "../../ui/Card";
import { RelativeTime } from "../../ui/RelativeTime";

type EndpointCardProps = {
  endpoint: Omit<EndpointView, "id">;
  node?: string;
};

export function EndpointCard({ endpoint, node }: EndpointCardProps) {
  const result = endpoint.last_result;
  const sshOpen = result?.ssh.open ?? null;
  return (
    <Card className="grid gap-3 rounded-card border-t-4 shadow-sm border-t-unknown">
      <div className="grid gap-0.5">
        <span className="font-semibold break-all">{endpoint.name}</span>
        <span className="text-xs text-muted break-all">
          {endpoint.host}:{endpoint.ssh_port}
          {endpoint.url ? ` · ${endpoint.url}` : ""}
        </span>
        {node && <span className="text-xs text-muted">Via {node}</span>}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="neutral">Server without NOC</Badge>
        {sshOpen === null && <span className="text-muted">Not checked yet</span>}
        {sshOpen === true && <Badge tone="ok">SSH answers</Badge>}
        {sshOpen === false && <Badge tone="critical">SSH does not answer</Badge>}
        {result?.web && <Badge tone={result.web.ok ? "ok" : "critical"}>Web {result.web.ok ? `HTTP ${result.web.status}` : "down"}</Badge>}
      </div>
      {endpoint.last_checked_at && (
        <p className="m-0 text-xs text-muted">
          Checked <RelativeTime iso={endpoint.last_checked_at} />
        </p>
      )}
    </Card>
  );
}
