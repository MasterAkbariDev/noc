import { useId, type ReactNode } from "react";

type SectionProps = {
  heading: string;
  children: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
};

export function Section({ heading, children, description, actions }: SectionProps) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="m-0 mb-8 grid gap-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="grid gap-0.5">
          <h2 id={headingId} className="m-0 text-base font-semibold">
            {heading}
          </h2>
          {description !== undefined && <p className="m-0 text-sm text-muted">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}
