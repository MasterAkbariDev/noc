import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type EmptyStateProps = {
  icon?: LucideIcon;
  title: string;
  text?: string;
  action?: ReactNode;
};

export function EmptyState({ icon: Icon, title, text, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
      {Icon !== undefined && (
        <span aria-hidden="true" className="mb-1 inline-grid size-11 place-items-center rounded-full bg-surface-2 text-muted">
          <Icon size={22} />
        </span>
      )}
      <p className="m-0 font-semibold">{title}</p>
      {text !== undefined && <p className="m-0 max-w-md text-sm text-muted">{text}</p>}
      {action}
    </div>
  );
}
