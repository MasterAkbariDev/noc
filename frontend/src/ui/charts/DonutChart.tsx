import { useState } from "react";
import { cx } from "../../lib/cx";
import { List, ListItem } from "../List";
import { ChartFrame, Swatch } from "./ChartFrame";
import { fullNumber } from "./scale";

const SIZE = 168;
const STROKE = 20;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const GAP = 2;
const CENTER = SIZE / 2;

export type DonutItem = { key: string; label: string; value: number; color: string };

export type DonutSegment = { item: DonutItem; dash: number; offset: number };

type DonutChartProps = {
  title: string;
  subtitle?: string;
  items: DonutItem[];
  centerLabel: string;
  firstColumn: string;
  valueColumn: string;
  empty: string;
  className?: string;
};

export function donutSegments(items: DonutItem[]): DonutSegment[] {
  const shown = items.filter((item) => item.value > 0);
  const total = shown.reduce((sum, item) => sum + item.value, 0);
  if (total === 0) {
    return [];
  }
  const gap = shown.length > 1 ? GAP : 0;
  let offset = 0;
  return shown.map((item) => {
    const length = (item.value / total) * CIRCUMFERENCE;
    const segment = { item, dash: Math.max(0.5, length - gap), offset };
    offset += length;
    return segment;
  });
}

export function shareText(value: number, total: number): string {
  return total === 0 ? "0%" : `${Math.round((value / total) * 100)}%`;
}

export function DonutChart({ title, subtitle, items, centerLabel, firstColumn, valueColumn, empty, className }: DonutChartProps) {
  const [active, setActive] = useState<string | null>(null);
  const total = items.reduce((sum, item) => sum + item.value, 0);
  const segments = donutSegments(items);
  const activeItem = items.find((item) => item.key === active);
  const summary = items.map((item) => `${item.label} ${fullNumber(item.value)}`).join(", ");
  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      series={[]}
      className={className}
      columns={[firstColumn, valueColumn, "Share"]}
      rows={items.map((item) => ({
        key: item.key,
        label: item.label,
        values: [fullNumber(item.value), shareText(item.value, total)],
      }))}
    >
      {total === 0 ? (
        <p className="m-0 text-sm text-muted">{empty}</p>
      ) : (
        <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-4">
          <div className="relative shrink-0" onMouseLeave={() => setActive(null)}>
            <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`${title}: ${summary}`}>
              <circle cx={CENTER} cy={CENTER} r={RADIUS} fill="none" stroke="var(--ui-surface-2)" strokeWidth={STROKE} />
              {segments.map((segment) => (
                <circle
                  key={segment.item.key}
                  cx={CENTER}
                  cy={CENTER}
                  r={RADIUS}
                  fill="none"
                  stroke={segment.item.color}
                  strokeWidth={active === segment.item.key ? STROKE + 4 : STROKE}
                  strokeDasharray={`${segment.dash} ${CIRCUMFERENCE - segment.dash}`}
                  strokeDashoffset={-segment.offset}
                  transform={`rotate(-90 ${CENTER} ${CENTER})`}
                  opacity={active === null || active === segment.item.key ? 1 : 0.35}
                  className="cursor-pointer transition-[opacity,stroke-width]"
                  onMouseEnter={() => setActive(segment.item.key)}
                />
              ))}
            </svg>
            <div aria-hidden="true" className="pointer-events-none absolute inset-0 grid place-content-center text-center">
              <span className="text-2xl leading-tight font-semibold tabular-nums">
                {fullNumber(activeItem?.value ?? total)}
              </span>
              <span className="max-w-24 text-xs text-muted">{activeItem?.label ?? centerLabel}</span>
            </div>
          </div>
          <List label="Legend" gap="sm" className="min-w-40 max-w-xs flex-1 text-sm">
            {items.map((item) => (
              <ListItem
                key={item.key}
                className={cx(
                  "flex items-center gap-2 rounded-control px-1.5 py-0.5 transition-colors",
                  active === item.key && "bg-surface-2",
                )}
              >
                <Swatch color={item.color} />
                <span className="min-w-0 flex-1 truncate" title={item.label}>
                  {item.label}
                </span>
                <span className="font-semibold tabular-nums">{fullNumber(item.value)}</span>
                <span className="w-10 text-right text-xs text-muted tabular-nums">{shareText(item.value, total)}</span>
              </ListItem>
            ))}
          </List>
        </div>
      )}
    </ChartFrame>
  );
}
