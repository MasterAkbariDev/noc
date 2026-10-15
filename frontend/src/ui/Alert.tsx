import { CircleAlert, CircleCheck, Info, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "../lib/cx";
import type { Tone } from "../lib/tones";

const BOX_CLASSES: Record<Tone, string> = {
  critical: "border-critical/40 bg-critical-soft",
  warning: "border-warning/40 bg-warning-soft",
  info: "border-info/40 bg-info-soft",
  ok: "border-ok/40 bg-ok-soft",
  neutral: "border-border bg-surface-2",
  unknown: "border-unknown/40 bg-unknown-soft",
};

const ICON_CLASSES: Record<Tone, string> = {
  critical: "text-critical",
  warning: "text-warning",
  info: "text-info",
  ok: "text-ok",
  neutral: "text-muted",
  unknown: "text-unknown",
};

const DEFAULT_ICONS: Record<Tone, LucideIcon> = {
  critical: CircleAlert,
  warning: TriangleAlert,
  info: Info,
  ok: CircleCheck,
  neutral: Info,
  unknown: Info,
};

type AlertProps = {
  tone: Tone;
  children: ReactNode;
  title?: ReactNode;
  icon?: LucideIcon;
  action?: ReactNode;
  role?: "status" | "alert";
  label?: string;
  size?: "md" | "lg";
};

export function Alert({ tone, children, title, icon, action, role, label, size = "md" }: AlertProps) {
  const Icon = icon ?? DEFAULT_ICONS[tone];
  return (
    <section
      role={role}
      aria-label={label}
      className={cx("flex flex-wrap items-center gap-3 rounded-card border", size === "lg" ? "p-4" : "px-3 py-2", BOX_CLASSES[tone])}
    >
      <Icon aria-hidden="true" size={size === "lg" ? 24 : 18} strokeWidth={2.25} className={cx("shrink-0", ICON_CLASSES[tone])} />
      <div className="grid min-w-0 flex-1 basis-48 gap-0.5 text-sm">
        {title !== undefined && <p className={cx("m-0 font-semibold break-words", size === "lg" && "text-lg")}>{title}</p>}
        {children}
      </div>
      {action}
    </section>
  );
}
