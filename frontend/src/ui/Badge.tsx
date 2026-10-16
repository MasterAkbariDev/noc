import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "../lib/cx";
import type { Tone } from "../lib/tones";

const TONE_CLASSES: Record<Tone, string> = {
  critical: "bg-critical-soft text-critical",
  warning: "bg-warning-soft text-warning",
  info: "bg-info-soft text-info",
  ok: "bg-ok-soft text-ok",
  neutral: "bg-surface-2 text-fg",
  unknown: "bg-unknown-soft text-unknown",
};

type BadgeProps = {
  tone: Tone;
  icon?: LucideIcon;
  children: ReactNode;
  className?: string;
};

export function Badge({ tone, icon: Icon, children, className }: BadgeProps) {
  return (
    <span
      className={cx(
        "inline-flex max-w-full items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold whitespace-nowrap",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {Icon !== undefined && <Icon aria-hidden="true" size={14} strokeWidth={2.25} />}
      {children}
    </span>
  );
}
