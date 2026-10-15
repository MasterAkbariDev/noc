import type { CSSProperties } from "react";
import { cx } from "../lib/cx";
import type { Tone } from "../lib/tones";

const FILL_CLASSES: Record<Tone, string> = {
  critical: "bg-critical",
  warning: "bg-warning",
  info: "bg-info",
  ok: "bg-ok",
  neutral: "bg-accent",
  unknown: "bg-unknown",
};

type MeterProps = {
  label: string;
  value: number;
  valueText: string;
  tone?: Tone;
  size?: "sm" | "md";
};

export function Meter({ label, value, valueText, tone = "neutral", size = "md" }: MeterProps) {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={clamped}
      aria-valuetext={valueText}
      className={cx("w-full overflow-hidden rounded-full bg-surface-2", size === "sm" ? "h-1.5" : "h-2")}
    >
      <div
        className={cx("h-full w-(--meter-width) rounded-full transition-[width]", FILL_CLASSES[tone])}
        style={{ "--meter-width": `${clamped}%` } as CSSProperties}
      />
    </div>
  );
}
