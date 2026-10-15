import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  status?: ReactNode;
  actions?: ReactNode;
  eyebrow?: string;
};

export function PageHeader({ title, status, actions, eyebrow }: PageHeaderProps) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {eyebrow !== undefined && (
          <p className="m-0 mb-1 text-xs font-semibold tracking-wider text-accent uppercase">{eyebrow}</p>
        )}
        <h1 className="m-0 text-2xl font-semibold tracking-tight break-words">{title}</h1>
        {status !== undefined && <div className="mt-1 text-sm text-muted">{status}</div>}
      </div>
      {actions !== undefined && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
