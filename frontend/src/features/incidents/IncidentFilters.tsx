import { severityView } from "../../lib/tones";
import { buttonClass } from "../../ui";
import { FILTER_LABELS, INCIDENT_FILTERS, type IncidentFilter } from "./filters";

type IncidentFiltersProps = {
  filter: IncidentFilter;
  severity: string;
  severities: string[];
  search: string;
  onFilterChange: (filter: IncidentFilter) => void;
  onSeverityChange: (severity: string) => void;
  onSearchChange: (search: string) => void;
};

export function IncidentFilters({
  filter,
  severity,
  severities,
  search,
  onFilterChange,
  onSeverityChange,
  onSearchChange,
}: IncidentFiltersProps) {
  return (
    <div className="mb-4 flex flex-wrap items-end gap-3">
      <div role="group" aria-label="Show" className="flex flex-wrap gap-2">
        {INCIDENT_FILTERS.map((option) => {
          const pressed = option === filter;
          return (
            <button
              key={option}
              type="button"
              aria-pressed={pressed}
              onClick={() => onFilterChange(option)}
              className={buttonClass({ variant: pressed ? "primary" : "secondary", size: "sm" })}
            >
              {FILTER_LABELS[option]}
            </button>
          );
        })}
      </div>
      <label className="grid gap-1 text-sm text-muted">
        Severity
        <select
          value={severity}
          onChange={(event) => onSeverityChange(event.target.value)}
          className="rounded-control border border-border bg-surface px-2 py-1.5 text-sm text-fg"
        >
          <option value="">All severities</option>
          {severities.map((value) => (
            <option key={value} value={value}>
              {severityView(value).label}
            </option>
          ))}
        </select>
      </label>
      <label className="grid min-w-0 flex-1 gap-1 text-sm text-muted sm:max-w-xs">
        Search
        <input
          type="search"
          value={search}
          placeholder="Title or target"
          onChange={(event) => onSearchChange(event.target.value)}
          className="rounded-control border border-border bg-surface px-2 py-1.5 text-sm text-fg"
        />
      </label>
    </div>
  );
}
