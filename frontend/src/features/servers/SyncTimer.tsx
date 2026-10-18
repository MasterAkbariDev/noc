import { useEffect, useState } from "react";
import { PEERS_POLL_MS, usePeersQuery } from "../nodes/queries";

// Counts down to the next automatic sync of the other NOCs (the peers poll).
export function SyncTimer() {
  const query = usePeersQuery();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  if (!query.isSuccess || query.dataUpdatedAt === 0) {
    return null;
  }
  const seconds = Math.max(0, Math.ceil((query.dataUpdatedAt + PEERS_POLL_MS - now) / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = String(seconds % 60).padStart(2, "0");
  return (
    <p className="m-0 text-sm text-muted" role="timer" aria-label="Time until the next sync">
      Next sync of the other NOCs in {minutes}:{rest}
    </p>
  );
}
