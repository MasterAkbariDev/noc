import { useMutation, useQueryClient } from "@tanstack/react-query";
import { checkEndpoint } from "../../api/client";
import type { EndpointView } from "../../api/types";
import { useSession } from "../../auth/session";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Card } from "../../ui/Card";
import { RelativeTime } from "../../ui/RelativeTime";
import { useToast } from "../../ui/Toaster";
import { settingsErrorText } from "../settings/accountView";

type EndpointCardProps = {
  endpoint: Omit<EndpointView, "id"> & { id?: string };
  node?: string;
};

// A server without a NOC: its SSH and web checks, with a button to check it again now.
export function EndpointCard({ endpoint, node }: EndpointCardProps) {
  const { me } = useSession();
  const queryClient = useQueryClient();
  const toast = useToast();
  const check = useMutation({
    mutationFn: () => checkEndpoint(endpoint.id ?? ""),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["endpoints"] }),
    onError: (error) => toast.error(settingsErrorText(error)),
  });
  const result = endpoint.last_result;
  const sshOpen = result?.ssh.open ?? null;
  const canCheck = me.role === "admin" && endpoint.id !== undefined;
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
      {canCheck && (
        <div className="flex justify-end border-t border-border pt-3">
          <Button size="sm" aria-label={`Check ${endpoint.name}`} disabled={check.isPending} onClick={() => check.mutate()}>
            Check now
          </Button>
        </div>
      )}
    </Card>
  );
}
