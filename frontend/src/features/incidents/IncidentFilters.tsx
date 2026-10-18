import { severityView } from "../../lib/tones";
import { Field, FilterBar, SegmentedControl, Select, TextInput } from "../../ui";
import { FILTER_LABELS, INCIDENT_FILTERS, type IncidentFilter } from "./filters";

type IncidentFiltersProps = {
  filter: IncidentFilter;
  severity: string;
  severities: string[];
  server: string;
  servers: string[];
  search: string;
  onFilterChange: (filter: IncidentFilter) => void;
  onSeverityChange: (severity: string) => void;
  onServerChange: (server: string) => void;
  onSearchChange: (search: string) => void;
};

export function IncidentFilters({
  filter,
  severity,
  severities,
  server,
  servers,
  search,
  onFilterChange,
  onSeverityChange,
  onServerChange,
  onSearchChange,
}: IncidentFiltersProps) {
  return (
    <FilterBar>
      <SegmentedControl
        label="Show"
        segments={INCIDENT_FILTERS.map((option) => ({ value: option, label: FILTER_LABELS[option] }))}
        value={filter}
        onChange={onFilterChange}
      />
      <Field label="Severity" compact>
        <Select
          compact
          value={severity}
          options={[
            { value: "", label: "All severities" },
            ...severities.map((value) => ({ value, label: severityView(value).label })),
          ]}
          onChange={(event) => onSeverityChange(event.target.value)}
        />
      </Field>
      <Field label="Server" compact>
        <Select
          compact
          aria-label="Server"
          value={server}
          options={[
            { value: "", label: "All servers" },
            ...servers.map((value) => ({ value, label: value })),
          ]}
          onChange={(event) => onServerChange(event.target.value)}
        />
      </Field>
      <Field label="Search" compact className="flex-1 sm:max-w-xs">
        <TextInput
          compact
          type="search"
          value={search}
          placeholder="Title or target"
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </Field>
    </FilterBar>
  );
}
