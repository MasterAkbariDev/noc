import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "../lib/cx";

type DisclosureProps = {
  summary: ReactNode;
  children: ReactNode;
  hint?: ReactNode;
  defaultOpen?: boolean;
  quiet?: boolean;
  className?: string;
};

export function Disclosure({ summary, children, hint, defaultOpen = false, quiet = false, className }: DisclosureProps) {
  return (
    <details open={defaultOpen} className={cx("disclosure group", !quiet && "rounded-card border border-border bg-surface", className)}>
      <summary
        className={cx(
          "flex cursor-pointer items-center gap-2 rounded-card text-sm font-medium select-none hover:text-accent",
          quiet ? "py-1 text-muted" : "px-4 py-3",
        )}
      >
        <ChevronRight aria-hidden="true" size={16} className="disclosure-chevron shrink-0" />
        <span className="min-w-0 flex-1">{summary}</span>
        {hint !== undefined && <span className="hidden text-sm font-normal text-muted sm:inline">{hint}</span>}
      </summary>
      <div className={quiet ? "pt-2" : "border-t border-border px-4 py-4"}>{children}</div>
    </details>
  );
}
