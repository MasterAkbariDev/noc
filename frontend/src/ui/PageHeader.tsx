import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  status?: ReactNode;
  actions?: ReactNode;
};

export function PageHeader({ title, status, actions }: PageHeaderProps) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="m-0 text-2xl font-semibold tracking-tight break-words">{title}</h1>
        {status !== undefined && <div className="mt-1 text-sm text-muted">{status}</div>}
      </div>
      {actions !== undefined && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
