import { useState, type PointerEvent } from "react";
import { ChartFrame } from "./ChartFrame";
import { Tooltip, type ColumnPoint } from "./ColumnChart";
import { compactNumber, fullNumber, labelEvery, niceScale } from "./scale";
import { useWidth } from "./useWidth";

const HEIGHT = 200;
const MARGIN = { top: 16, right: 48, bottom: 24, left: 40 };
const LABEL_ROOM_PX = 56;

type LineChartProps = {
  title: string;
  subtitle?: string;
  name: string;
  color: string;
  points: ColumnPoint[];
  firstColumn: string;
};

export function LineChart({ title, subtitle, name, color, points, firstColumn }: LineChartProps) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const plotWidth = Math.max(10, width - MARGIN.left - MARGIN.right);
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const values = points.map((point) => point.values[0] ?? 0);
  const scale = niceScale(Math.max(0, ...values));
  const step = points.length > 1 ? plotWidth / (points.length - 1) : 0;
  const x = (index: number) => MARGIN.left + step * index;
  const y = (value: number) => MARGIN.top + plotHeight - (value / scale.max) * plotHeight;
  const path = values.map((value, index) => `${index === 0 ? "M" : "L"}${x(index)},${y(value)}`).join(" ");
  const area = values.length > 0 ? `${path} L${x(values.length - 1)},${y(0)} L${x(0)},${y(0)} Z` : "";
  const every = labelEvery(points.length, Math.floor(plotWidth / LABEL_ROOM_PX));
  const last = values.length - 1;
  const activePoint = active === null ? undefined : points[active];

  function track(event: PointerEvent<SVGRectElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const offset = event.clientX - box.left;
    const index = step === 0 ? 0 : Math.round(offset / step);
    setActive(Math.min(points.length - 1, Math.max(0, index)));
  }

  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      series={[{ name, color }]}
      columns={[firstColumn, name]}
      rows={points.map((point, index) => ({
        key: point.key,
        label: point.longLabel,
        values: [fullNumber(values[index] ?? 0)],
      }))}
    >
      <div ref={ref} className="relative w-full min-w-0">
        <svg
          width="100%"
          height={HEIGHT}
          viewBox={`0 0 ${width} ${HEIGHT}`}
          role="img"
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
              <text x={MARGIN.left - 6} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-muted text-[11px]">
                {compactNumber(tick)}
              </text>
            </g>
          ))}
          {points.map(
            (point, index) =>
              index % every === 0 && (
                <text key={point.key} x={x(index)} y={HEIGHT - 6} textAnchor="middle" className="fill-muted text-[11px]">
                  {point.label}
                </text>
              ),
          )}
          <path d={area} fill={color} fillOpacity={0.1} />
          <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {last >= 0 && (
            <>
              <circle cx={x(last)} cy={y(values[last] ?? 0)} r={4} fill={color} stroke="var(--ui-surface)" strokeWidth={2} />
              <text x={x(last) + 8} y={y(values[last] ?? 0)} dy="0.32em" className="fill-fg text-[11px] font-semibold">
                {compactNumber(values[last] ?? 0)}
              </text>
            </>
          )}
          {active !== null && (
            <>
              <line
                x1={x(active)}
                x2={x(active)}
                y1={MARGIN.top}
                y2={MARGIN.top + plotHeight}
                stroke="var(--ui-muted)"
                strokeWidth={1}
              />
              <circle
                cx={x(active)}
                cy={y(values[active] ?? 0)}
                r={4}
                fill={color}
                stroke="var(--ui-surface)"
                strokeWidth={2}
              />
            </>
          )}
          <rect
            x={MARGIN.left - step / 2}
            y={MARGIN.top}
            width={plotWidth + step}
            height={plotHeight}
            fill="transparent"
            onPointerMove={track}
            onPointerLeave={() => setActive(null)}
          />
        </svg>
        {active !== null && activePoint !== undefined && (
          <Tooltip
            left={Math.min(width - 160, Math.max(0, x(active) - 80))}
            title={activePoint.longLabel}
            rows={[{ name, color, value: fullNumber(values[active] ?? 0) }]}
          />
        )}
      </div>
    </ChartFrame>
  );
}
