import { CircleHelp, ShieldAlert, ShieldCheck } from "lucide-react";
import { Badge, Button } from "../../ui";
import { chainView } from "./view";
import { useChainStatus } from "./queries";

export function ChainBadge() {
  const query = useChainStatus();

  if (query.data === undefined) {
    if (query.isError) {
      return (
        <span className="inline-flex flex-wrap items-center gap-2">
          <Badge tone="unknown" icon={CircleHelp}>
            Audit log not checked
          </Badge>
          <Button size="sm" variant="ghost" onClick={() => void query.refetch()}>
            Check again
          </Button>
        </span>
      );
    }
    return <Badge tone="unknown">Checking the audit log…</Badge>;
  }

  const view = chainView(query.data);
  return (
    <Badge tone={view.tone} icon={query.data.ok ? ShieldCheck : ShieldAlert}>
      {view.label}
    </Badge>
  );
}
