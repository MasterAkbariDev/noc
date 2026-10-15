import type { LucideIcon } from "lucide-react";
import { Link } from "react-router";
import type { ReactNode } from "react";
import { cx } from "../lib/cx";
import type { Tone } from "../lib/tones";
import { CardIcon } from "./Card";
import { Sparkline } from "./charts/Sparkline";

const VALUE_CLASSES: Record<Tone, string> = {
  critical: "text-critical",
  warning: "text-warning",
  info: "text-info",
  ok: "text-ok",
  neutral: "text-fg",
  unknown: "text-unknown",
};

const ACCENT_CLASSES: Record<Tone, string> = {
  critical: "before:bg-critical",
  warning: "before:bg-warning",
  info: "before:bg-info",
  ok: "before:bg-ok",
  neutral: "before:bg-accent",
  unknown: "before:bg-unknown",
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
        <span className={cx("text-3xl leading-none font-semibold tracking-tight tabular-nums", VALUE_CLASSES[tone])}>{value}</span>
        {trend !== undefined && trend.length > 1 && <Sparkline values={trend} />}
      </span>
      {hint !== undefined && <span className="text-xs text-muted">{hint}</span>}
    </>
  );
  const tileClass = cx(
    "relative m-0 flex min-w-0 flex-col gap-2 overflow-hidden rounded-card border border-border bg-surface p-4 shadow-card",
    "before:absolute before:inset-x-0 before:top-0 before:h-0.5 before:content-['']",
    ACCENT_CLASSES[tone],
  );
  if (to === undefined) {
    return <div className={tileClass}>{content}</div>;
  }
  return (
    <Link to={to} className={cx(tileClass, "transition-colors hover:border-border-strong hover:bg-surface-2")}>
      {content}
    </Link>
  );
}
