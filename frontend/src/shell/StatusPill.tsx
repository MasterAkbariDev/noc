import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { getOverview } from "../api/client";
import { cx } from "../lib/cx";
import { overviewTone, type Tone } from "../lib/tones";
import { StatusDot } from "../ui/StatusDot";

export const OVERVIEW_POLL_MS = 30000;

const PILL_CLASS = "inline-flex max-w-full items-center rounded-full border px-3 py-1 text-sm font-medium";

const PILL_TONES: Record<Tone, string> = {
  critical: "border-critical/30 bg-critical-soft",
  warning: "border-warning/30 bg-warning-soft",
  info: "border-info/30 bg-info-soft",
  ok: "border-ok/30 bg-ok-soft",
  neutral: "border-border bg-surface-2",
  unknown: "border-border bg-surface-2",
};

function UnknownPill({ label }: { label: string }) {
  return (
    <span className={cx(PILL_CLASS, PILL_TONES.unknown)}>
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
  const tone = overviewTone(verdict.level);
  return (
    <Link to="/" className={cx(PILL_CLASS, PILL_TONES[tone], "hover:brightness-95")}>
      <StatusDot tone={tone} label={verdict.sentence} showLabel />
    </Link>
  );
}
