import { useState, type PointerEvent } from "react";
import { clockTime } from "../../lib/format";
import { ChartFrame } from "./ChartFrame";
import { Tooltip } from "./ColumnChart";
import { niceScale } from "./scale";
import { useWidth } from "./useWidth";

const HEIGHT = 180;
const MARGIN = { top: 12, right: 16, bottom: 24, left: 64 };
const TIME_TICKS = 5;
const GAP_STEPS = 3;

export type TimePoint = [number, number];

export type TimeSeries = { name: string; color: string; points: TimePoint[] };

type TimeChartProps = {
  title: string;
  subtitle?: string;
  series: TimeSeries[];
  from: number;
  to: number;
  step: number;
  format: (value: number) => string;
  max?: number;
  empty?: string;
};

export function timePath(points: TimePoint[], x: (time: number) => number, y: (value: number) => number, gap: number): string {
  return points
    .map(([time, value], index) => {
      const previous = points[index - 1];
      const jump = previous === undefined || time - previous[0] > gap;
      return `${jump ? "M" : "L"}${x(time).toFixed(1)},${y(value).toFixed(1)}`;
    })
    .join(" ");
}

export function nearestIndex(points: TimePoint[], time: number): number | null {
  let best: number | null = null;
  let distance = Number.POSITIVE_INFINITY;
  points.forEach(([stamp], index) => {
    const away = Math.abs(stamp - time);
    if (away < distance) {
      distance = away;
      best = index;
    }
  });
  return best;
}

function valueAt(points: TimePoint[], time: number): number | undefined {
  return points.find(([stamp]) => stamp === time)?.[1];
}

export function TimeChart({ title, subtitle, series, from, to, step, format, max, empty = "No readings in this time range." }: TimeChartProps) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [activeTime, setActiveTime] = useState<number | null>(null);
  const plotWidth = Math.max(10, width - MARGIN.left - MARGIN.right);
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const allValues = series.flatMap((item) => item.points.map(([, value]) => value));
  const scale = niceScale(max ?? Math.max(0, ...allValues));
  const top = max ?? scale.max;
  const span = Math.max(1, to - from);
  const x = (time: number) => MARGIN.left + ((time - from) / span) * plotWidth;
  const y = (value: number) => MARGIN.top + plotHeight - (Math.min(value, top) / top) * plotHeight;
  const ticks = max === undefined ? scale.ticks : [0, max / 2, max];
  const times = Array.from({ length: TIME_TICKS }, (_, index) => from + (span * index) / (TIME_TICKS - 1));
  const reference = series[0]?.points ?? [];
  const hasData = allValues.length > 0;

  function track(event: PointerEvent<SVGRectElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const time = from + ((event.clientX - box.left) / box.width) * span;
    const index = nearestIndex(reference, time);
    setActiveTime(index === null ? null : (reference[index]?.[0] ?? null));
  }

  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      series={series.map(({ name, color }) => ({ name, color }))}
      columns={["Time", ...series.map((item) => item.name)]}
      rows={reference.map(([time]) => ({
        key: String(time),
        label: clockTime(time),
        values: series.map((item) => {
          const value = valueAt(item.points, time);
          return value === undefined ? "–" : format(value);
        }),
      }))}
    >
      <div ref={ref} dir="ltr" className="relative w-full min-w-0">
        {!hasData ? (
          <p className="m-0 grid h-[180px] place-items-center text-sm text-muted">{empty}</p>
        ) : (
          <svg width="100%" height={HEIGHT} viewBox={`0 0 ${width} ${HEIGHT}`} role="img" aria-label={title} className="block overflow-visible">
            {ticks.map((tick) => (
              <g key={tick}>
                <line x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={y(tick)} y2={y(tick)} stroke="var(--ui-chart-grid)" strokeWidth={1} />
                <text x={MARGIN.left - 6} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-muted text-[11px]">
                  {format(tick)}
                </text>
              </g>
            ))}
            {times.map((time, index) => (
              <text
                key={time}
                x={x(time)}
                y={HEIGHT - 6}
                textAnchor={index === 0 ? "start" : index === TIME_TICKS - 1 ? "end" : "middle"}
                className="fill-muted text-[11px]"
              >
                {clockTime(time)}
              </text>
            ))}
            {series.map((item) => (
              <path
                key={item.name}
                d={timePath(item.points, x, y, step * GAP_STEPS)}
                fill="none"
                stroke={item.color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            ))}
            {activeTime !== null && (
              <>
                <line x1={x(activeTime)} x2={x(activeTime)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} stroke="var(--ui-muted)" strokeWidth={1} />
                {series.map((item) => {
                  const value = valueAt(item.points, activeTime);
                  return (
                    value !== undefined && (
                      <circle key={item.name} cx={x(activeTime)} cy={y(value)} r={4} fill={item.color} stroke="var(--ui-surface)" strokeWidth={2} />
                    )
                  );
                })}
              </>
            )}
            <rect
              x={MARGIN.left}
              y={MARGIN.top}
              width={plotWidth}
              height={plotHeight}
              fill="transparent"
              onPointerMove={track}
              onPointerLeave={() => setActiveTime(null)}
            />
          </svg>
        )}
        {activeTime !== null && (
          <Tooltip
            left={Math.min(width - 160, Math.max(0, x(activeTime) - 80))}
            title={clockTime(activeTime)}
            rows={series.flatMap((item) => {
              const value = valueAt(item.points, activeTime);
              return value === undefined ? [] : [{ name: item.name, color: item.color, value: format(value) }];
            })}
          />
        )}
      </div>
    </ChartFrame>
  );
}
