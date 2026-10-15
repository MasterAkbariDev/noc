import type { ReactNode } from "react";
import { Link } from "react-router";
import { usePrefetchIncident } from "./prefetch";

type IncidentLinkProps = {
  id: string;
  className?: string;
  children: ReactNode;
};

export function IncidentLink({ id, className, children }: IncidentLinkProps) {
  const prefetch = usePrefetchIncident();
  return (
    <Link
      to={`/incidents/${encodeURIComponent(id)}`}
      className={className}
      onMouseEnter={() => prefetch(id)}
      onFocus={() => prefetch(id)}
    >
      {children}
    </Link>
  );
}
