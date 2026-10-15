import { useState } from "react";
import { ChartFrame, type ChartSeries } from "./ChartFrame";
import { compactNumber, fullNumber, labelEvery, niceScale } from "./scale";
import { useWidth } from "./useWidth";

const HEIGHT = 200;
const MARGIN = { top: 12, right: 8, bottom: 24, left: 40 };
const MAX_BAR = 24;
const BAR_GAP = 2;
const RADIUS = 4;
const LABEL_ROOM_PX = 56;

export type ColumnPoint = { key: string; label: string; longLabel: string; values: number[] };

type ColumnChartProps = {
  title: string;
  subtitle?: string;
  series: ChartSeries[];
  points: ColumnPoint[];
  firstColumn: string;
  className?: string;
};

export function columnPath(x: number, y: number, width: number, height: number): string {
  if (height <= 0) {
    return "";
  }
  const r = Math.min(RADIUS, width / 2, height);
  const bottom = y + height;
  return [
    `M${x},${bottom}`,
    `V${y + r}`,
    `Q${x},${y} ${x + r},${y}`,
    `H${x + width - r}`,
    `Q${x + width},${y} ${x + width},${y + r}`,
    `V${bottom}`,
    "Z",
  ].join(" ");
}

export function ColumnChart({ title, subtitle, series, points, firstColumn, className }: ColumnChartProps) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const plotWidth = Math.max(10, width - MARGIN.left - MARGIN.right);
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const maxValue = Math.max(0, ...points.flatMap((point) => point.values));
  const scale = niceScale(maxValue);
  const band = plotWidth / Math.max(1, points.length);
  const barWidth = Math.max(2, Math.min(MAX_BAR, (band * 0.7 - BAR_GAP * (series.length - 1)) / series.length));
  const groupWidth = barWidth * series.length + BAR_GAP * (series.length - 1);
  const every = labelEvery(points.length, Math.floor(plotWidth / LABEL_ROOM_PX));
  const y = (value: number) => MARGIN.top + plotHeight - (value / scale.max) * plotHeight;
  const activePoint = active === null ? undefined : points[active];

  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      className={className}
      series={series}
      columns={[firstColumn, ...series.map((item) => item.name)]}
      rows={points.map((point) => ({
        key: point.key,
        label: point.longLabel,
        values: point.values.map(fullNumber),
      }))}
    >
      <div ref={ref} className="relative w-full min-w-0" onMouseLeave={() => setActive(null)}>
        <svg
          width="100%"
          height={HEIGHT}
          viewBox={`0 0 ${width} ${HEIGHT}`}
          role="group"
          aria-label={title}
          className="block overflow-visible"
        >
          {scale.ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={MARGIN.left}
                x2={MARGIN.left + plotWidth}
                y1={y(tick)}
                y2={y(tick)}
                stroke="var(--ui-chart-grid)"
                strokeWidth={1}
              />
              <text
                x={MARGIN.left - 6}
                y={y(tick)}
                dy="0.32em"
                textAnchor="end"
                className="fill-muted text-[11px] tabular-nums"
              >
                {compactNumber(tick)}
              </text>
            </g>
          ))}
          {points.map((point, index) => {
            const left = MARGIN.left + band * index + (band - groupWidth) / 2;
            return (
              <g key={point.key}>
                {active === index && (
                  <rect
                    x={MARGIN.left + band * index}
                    y={MARGIN.top}
                    width={band}
                    height={plotHeight}
                    fill="var(--ui-surface-2)"
                  />
                )}
                {point.values.map((value, seriesIndex) => (
                  <path
                    key={series[seriesIndex]?.name ?? seriesIndex}
                    d={columnPath(left + seriesIndex * (barWidth + BAR_GAP), y(value), barWidth, y(0) - y(value))}
                    fill={series[seriesIndex]?.color}
                  />
                ))}
                {index % every === 0 && (
                  <text
                    x={MARGIN.left + band * index + band / 2}
                    y={HEIGHT - 6}
                    textAnchor="middle"
                    className="fill-muted text-[11px]"
                  >
                    {point.label}
                  </text>
                )}
                <rect
                  x={MARGIN.left + band * index}
                  y={MARGIN.top}
                  width={band}
                  height={plotHeight}
                  fill="transparent"
                  tabIndex={0}
                  role="img"
                  aria-label={`${point.longLabel}: ${series
                    .map((item, seriesIndex) => `${item.name} ${fullNumber(point.values[seriesIndex] ?? 0)}`)
                    .join(", ")}`}
                  onMouseEnter={() => setActive(index)}
                  onFocus={() => setActive(index)}
                  onBlur={() => setActive(null)}
                />
              </g>
            );
          })}
          <line
            x1={MARGIN.left}
            x2={MARGIN.left + plotWidth}
            y1={y(0)}
            y2={y(0)}
            stroke="var(--ui-border)"
            strokeWidth={1}
          />
        </svg>
        {active !== null && activePoint !== undefined && (
          <Tooltip
            left={Math.min(width - 160, Math.max(0, MARGIN.left + band * active + band / 2 - 80))}
            title={activePoint.longLabel}
            rows={series.map((item, seriesIndex) => ({
              name: item.name,
              color: item.color,
              value: fullNumber(activePoint.values[seriesIndex] ?? 0),
            }))}
          />
        )}
      </div>
    </ChartFrame>
  );
}

type TooltipRow = { name: string; color: string; value: string };

export function Tooltip({ left, title, rows }: { left: number; title: string; rows: TooltipRow[] }) {
  return (
    <div
      role="status"
      className="pointer-events-none absolute top-0 z-10 w-40 rounded-control border border-border bg-surface p-2 text-xs shadow-raised"
      style={{ left }}
    >
      <p className="m-0 mb-1 text-muted">{title}</p>
      {rows.map((row) => (
        <p key={row.name} className="m-0 flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-0.5 w-3" style={{ background: row.color }} />
          <span className="font-semibold tabular-nums">{row.value}</span>
          <span className="text-muted">{row.name}</span>
        </p>
      ))}
    </div>
  );
}
