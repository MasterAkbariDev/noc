import type { LucideIcon } from "lucide-react";
import { useId, type ReactNode } from "react";
import { cx } from "../lib/cx";
import type { Tone } from "../lib/tones";

const ICON_CLASSES: Record<Tone, string> = {
  critical: "bg-critical-soft text-critical",
  warning: "bg-warning-soft text-warning",
  info: "bg-info-soft text-info",
  ok: "bg-ok-soft text-ok",
  neutral: "bg-accent-soft text-accent",
  unknown: "bg-unknown-soft text-unknown",
};

type CardProps = {
  title?: string;
  subtitle?: ReactNode;
  icon?: LucideIcon;
  iconTone?: Tone;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
};

export function CardIcon({ icon: Icon, tone = "neutral" }: { icon: LucideIcon; tone?: Tone }) {
  return (
    <span aria-hidden="true" className={cx("inline-grid size-8 shrink-0 place-items-center rounded-control", ICON_CLASSES[tone])}>
      <Icon size={16} strokeWidth={2.25} />
    </span>
  );
}

export function Card({ title, subtitle, icon, iconTone, actions, children, className, flush = false }: CardProps) {
  const titleId = useId();
  const hasHeader = title !== undefined || actions !== undefined;
  return (
    <section
      aria-labelledby={title === undefined ? undefined : titleId}
      className={cx("m-0 min-w-0 rounded-card border border-border bg-surface shadow-card", !flush && "p-5", className)}
    >
      {hasHeader && (
        <header className={cx("mb-4 flex flex-wrap items-center justify-between gap-2", flush && "mb-0 border-b border-border px-5 py-4")}>
          <div className="flex min-w-0 items-center gap-3">
            {icon !== undefined && <CardIcon icon={icon} tone={iconTone} />}
            <div className="grid min-w-0 gap-0.5">
              {title !== undefined && (
                <h2 id={titleId} className="m-0 text-base font-semibold break-words">
                  {title}
                </h2>
              )}
              {subtitle !== undefined && <p className="m-0 text-xs text-muted">{subtitle}</p>}
            </div>
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}
