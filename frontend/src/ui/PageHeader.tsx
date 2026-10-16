import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  status?: ReactNode;
  actions?: ReactNode;
};

export function PageHeader({ title, status, actions }: PageHeaderProps) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0 max-w-2xl">
        <h1 className="m-0 text-[28px] leading-tight font-semibold tracking-tight break-words">{title}</h1>
        {status !== undefined && <div className="mt-1.5 text-base text-muted">{status}</div>}
      </div>
      {actions !== undefined && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
