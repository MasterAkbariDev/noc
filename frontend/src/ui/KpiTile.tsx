import type { LucideIcon } from "lucide-react";
import { Link } from "react-router";
import type { ReactNode } from "react";
import { cx } from "../lib/cx";
import type { Tone } from "../lib/tones";
import { CardIcon } from "./Card";
import { CountUp } from "./CountUp";
import { Sparkline } from "./charts/Sparkline";

const VALUE_CLASSES: Record<Tone, string> = {
  critical: "text-critical",
  warning: "text-warning",
  info: "text-info",
  ok: "text-ok",
  neutral: "text-fg",
  unknown: "text-unknown",
};

type KpiTileProps = {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: Tone;
  to?: string;
  icon?: LucideIcon;
  trend?: number[];
};

export function KpiTile({ label, value, hint, tone = "neutral", to, icon, trend }: KpiTileProps) {
  const content = (
    <>
      <span className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium text-muted">{label}</span>
        {icon !== undefined && <CardIcon icon={icon} tone={tone} />}
      </span>
      <span className="flex items-end justify-between gap-3">
        <span className={cx("text-3xl leading-none font-semibold tracking-tight tabular-nums", VALUE_CLASSES[tone])}>
          {typeof value === "number" ? <CountUp value={value} /> : value}
        </span>
        {trend !== undefined && trend.length > 1 && <Sparkline values={trend} />}
      </span>
      {hint !== undefined && <span className="text-xs text-muted">{hint}</span>}
    </>
  );
  const tileClass = "relative m-0 flex min-w-0 flex-col gap-2 overflow-hidden rounded-card border border-border bg-surface p-4";
  if (to === undefined) {
    return <div className={tileClass}>{content}</div>;
  }
  return (
    <Link to={to} className={cx(tileClass, "lift hover:border-border-strong")}>
      {content}
    </Link>
  );
}
