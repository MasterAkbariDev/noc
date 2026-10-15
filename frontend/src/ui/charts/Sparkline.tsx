const WIDTH = 88;
const HEIGHT = 28;
const PAD = 3;

export function sparkPath(values: number[], width = WIDTH, height = HEIGHT): string {
  const max = Math.max(1, ...values);
  const step = values.length > 1 ? (width - PAD * 2) / (values.length - 1) : 0;
  return values
    .map((value, index) => {
      const x = PAD + step * index;
      const y = height - PAD - (Math.max(0, value) / max) * (height - PAD * 2);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function Sparkline({ values, color = "var(--ui-chart-1)" }: { values: number[]; color?: string }) {
  const path = sparkPath(values);
  return (
    <svg aria-hidden="true" width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="shrink-0 overflow-visible">
      <path d={`${path} L${WIDTH - PAD},${HEIGHT - PAD} L${PAD},${HEIGHT - PAD} Z`} fill={color} fillOpacity={0.12} />
      <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
