import type { LiveRange } from "../../api/types";
import { Select } from "../../ui";
import { RANGE_OPTIONS, parseRange } from "./range";

export function RangeSelect({ value, onChange }: { value: LiveRange; onChange: (range: LiveRange) => void }) {
  return (
    <Select
      compact
      aria-label="Time range"
      options={RANGE_OPTIONS}
      value={value}
      onChange={(event) => onChange(parseRange(event.target.value))}
    />
  );
}
