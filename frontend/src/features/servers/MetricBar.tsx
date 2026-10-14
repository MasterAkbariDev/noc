import type { CSSProperties } from "react";
import type { ServerMetrics } from "../../api/types";
import { cx } from "../../lib/cx";
import { percentFromHundred } from "../../lib/format";
import { clampPercent, isAttention } from "./serverView";

type MetricBarProps = {
  label: string;
  value: number | null;
};

export function MetricBar({ label, value }: MetricBarProps) {
  if (value === null) {
    return (
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="text-muted">{label}</span>
        <span className="text-muted">No data</span>
      </div>
    );
  }
  const valueText = percentFromHundred(value);
  return (
    <div className="grid gap-1">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="text-muted">{label}</span>
        <span className="font-semibold tabular-nums">{valueText}</span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={clampPercent(value)}
        aria-valuetext={valueText}
        className="h-2 overflow-hidden rounded-full bg-surface-2"
      >
        <div
          className={cx("h-full w-(--bar-width) rounded-full", isAttention(value) ? "bg-critical" : "bg-accent")}
          style={{ "--bar-width": `${clampPercent(value)}%` } as CSSProperties}
        />
      </div>
    </div>
  );
}

export function MetricBars({ metrics }: { metrics: ServerMetrics | null }) {
  if (metrics === null) {
    return <p className="m-0 text-sm text-muted">Metrics unavailable</p>;
  }
  const diskLabel = metrics.disk_mount === null ? "Disk" : `Disk (${metrics.disk_mount})`;
  return (
    <div className="grid gap-3">
      <MetricBar label="CPU" value={metrics.cpu_percent} />
      <MetricBar label="Memory" value={metrics.memory_percent} />
      <MetricBar label={diskLabel} value={metrics.disk_percent} />
    </div>
  );
}
