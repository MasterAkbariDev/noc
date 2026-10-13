import { useId, type ReactNode } from "react";
import { cx } from "../lib/cx";

type CardProps = {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function Card({ title, actions, children, className }: CardProps) {
  const titleId = useId();
  const hasHeader = title !== undefined || actions !== undefined;
  return (
    <section
      aria-labelledby={title === undefined ? undefined : titleId}
      className={cx("m-0 rounded-card border border-border bg-surface p-4 shadow-card", className)}
    >
      {hasHeader && (
        <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title !== undefined && (
            <h2 id={titleId} className="m-0 text-base font-semibold">
              {title}
            </h2>
          )}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}
