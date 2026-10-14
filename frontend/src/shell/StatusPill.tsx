import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { getOverview } from "../api/client";
import { cx } from "../lib/cx";
import { overviewTone } from "../lib/tones";
import { StatusDot } from "../ui/StatusDot";

export const OVERVIEW_POLL_MS = 30000;

const PILL_CLASS = "inline-flex max-w-full items-center rounded-full border border-border px-3 py-1 text-sm";

function UnknownPill({ label }: { label: string }) {
  return (
    <span className={PILL_CLASS}>
      <StatusDot tone="unknown" label={label} showLabel />
    </span>
  );
}

export function StatusPill() {
  const query = useQuery({
    queryKey: ["overview"],
    queryFn: () => getOverview(),
    refetchInterval: OVERVIEW_POLL_MS,
  });

  if (query.isPending) {
    return <UnknownPill label="Checking…" />;
  }
  if (query.isError) {
    return <UnknownPill label="Status unavailable" />;
  }

  const verdict = query.data.verdict;
  return (
    <Link to="/" className={cx(PILL_CLASS, "hover:bg-surface-2")}>
      <StatusDot tone={overviewTone(verdict.level)} label={verdict.sentence} showLabel />
    </Link>
  );
}
