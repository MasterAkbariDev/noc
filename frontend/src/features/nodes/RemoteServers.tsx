import type { PeerView } from "../../api/types";
import { Card } from "../../ui/Card";
import { Section } from "../../ui/Section";
import { usePeersQuery } from "./queries";
import { peerStatusText } from "./view";

const AUTOMATION_TEXT: Record<string, string> = {
  auto_safe: "Safe fixes run automatically",
  approval_required: "Fixes need approval",
  observe_only: "Observe only",
};

export function RemoteServers() {
  const query = usePeersQuery();
  if (!query.isSuccess) {
    return null;
  }
  const followed = query.data.filter((peer) => peer.direction === "follows" && peer.status === "paired");
  if (followed.length === 0) {
    return null;
  }
  return (
    <Section heading="Servers from other nodes">
      <p className="m-0 text-sm text-muted">
        Read only. Each node decides its own fixes, and these are shown here for reference.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {followed.map((peer) => (
          <RemoteNode key={peer.id} peer={peer} />
        ))}
      </div>
    </Section>
  );
}

function RemoteNode({ peer }: { peer: PeerView }) {
  const snapshot = peer.last_status;
  return (
    <Card title={snapshot?.node_name ?? peer.name}>
      <p className="m-0 text-sm">{peerStatusText(peer, Date.now())}</p>
      {snapshot !== null && (
        <>
          <ul className="m-0 mt-3 grid list-none gap-2 p-0">
            {snapshot.targets.map((target) => (
              <li key={target.name} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span className="break-all">
                  {target.name} <span className="text-xs text-muted">({target.environment})</span>
                </span>
                <span className="text-xs text-muted">
                  {target.halted ? "Halted" : (AUTOMATION_TEXT[target.automation] ?? target.automation)}
                </span>
              </li>
            ))}
          </ul>
          {snapshot.active_incidents.length > 0 && (
            <p className="m-0 mt-3 text-sm">
              Open incidents: {snapshot.active_incidents.map((incident) => incident.title).join("; ")}
            </p>
          )}
        </>
      )}
    </Card>
  );
}
