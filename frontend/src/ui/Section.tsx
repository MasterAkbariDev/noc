import { useId, type ReactNode } from "react";

export function Section({ heading, children }: { heading: string; children: ReactNode }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="m-0 mb-8 grid gap-3">
      <h2 id={headingId} className="m-0 text-base font-semibold">
        {heading}
      </h2>
      {children}
    </section>
  );
}
