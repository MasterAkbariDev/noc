import { Link } from "react-router";
import type { ReactNode } from "react";
import { cx } from "../lib/cx";
import type { Tone } from "../lib/tones";

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
};

export function KpiTile({ label, value, hint, tone = "neutral", to }: KpiTileProps) {
  const content = (
    <>
      <span className="text-sm text-muted">{label}</span>
      <span className={cx("text-2xl font-semibold tabular-nums", VALUE_CLASSES[tone])}>{value}</span>
      {hint !== undefined && <span className="text-xs text-muted">{hint}</span>}
    </>
  );
  const tileClass =
    "m-0 flex min-w-0 flex-col gap-1 rounded-card border border-border bg-surface p-4 shadow-card";
  if (to === undefined) {
    return <div className={tileClass}>{content}</div>;
  }
  return (
    <Link to={to} className={cx(tileClass, "hover:bg-surface-2")}>
      {content}
    </Link>
  );
}
