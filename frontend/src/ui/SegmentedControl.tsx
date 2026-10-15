import type { LucideIcon } from "lucide-react";
import { cx } from "../lib/cx";

export type Segment<Value extends string> = { value: Value; label: string; icon?: LucideIcon };

type SegmentedControlProps<Value extends string> = {
  label: string;
  segments: Segment<Value>[];
  value: Value;
  onChange: (value: Value) => void;
  iconOnly?: boolean;
};

export function SegmentedControl<Value extends string>({
  label,
  segments,
  value,
  onChange,
  iconOnly = false,
}: SegmentedControlProps<Value>) {
  return (
    <div role="group" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-control border border-border bg-surface-2 p-1">
      {segments.map((segment) => {
        const pressed = segment.value === value;
        const Icon = segment.icon;
        const hideText = iconOnly && Icon !== undefined;
        return (
          <button
            key={segment.value}
            type="button"
            aria-pressed={pressed}
            aria-label={hideText ? segment.label : undefined}
            title={hideText ? segment.label : undefined}
            onClick={() => onChange(segment.value)}
            className={cx(
              "inline-flex items-center gap-1.5 rounded-[0.375rem] text-sm font-medium transition-colors",
              hideText ? "p-1.5" : "px-3 py-1",
              pressed ? "bg-surface text-fg shadow-card" : "text-muted hover:text-fg",
            )}
          >
            {Icon !== undefined && <Icon aria-hidden="true" size={15} />}
            {!hideText && segment.label}
          </button>
        );
      })}
    </div>
  );
}
