import { cx } from "../lib/cx";
import type { Tone } from "../lib/tones";

const DOT_CLASSES: Record<Tone, string> = {
  critical: "bg-critical",
  warning: "bg-warning",
  info: "bg-info",
  ok: "bg-ok",
  neutral: "bg-muted",
  unknown: "bg-unknown",
};

const RING_CLASSES: Record<Tone, string> = {
  critical: "text-critical",
  warning: "text-warning",
  info: "text-info",
  ok: "text-ok",
  neutral: "text-muted",
  unknown: "text-unknown",
};

type StatusDotProps = {
  tone: Tone;
  label: string;
  showLabel?: boolean;
};

export function StatusDot({ tone, label, showLabel = false }: StatusDotProps) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden="true" className={cx("size-2.5 shrink-0 rounded-full ring-3 ring-current/15", DOT_CLASSES[tone], RING_CLASSES[tone])} />
      <span className={showLabel ? undefined : "sr-only"}>{label}</span>
    </span>
  );
}
