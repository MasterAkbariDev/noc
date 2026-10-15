import { List, ListItem } from "../List";
import { ChartFrame } from "./ChartFrame";
import { fullNumber } from "./scale";

export type BarItem = { key: string; label: string; value: number };

type HBarChartProps = {
  title: string;
  subtitle?: string;
  color: string;
  items: BarItem[];
  firstColumn: string;
  valueColumn: string;
  empty: string;
};

export function HBarChart({ title, subtitle, color, items, firstColumn, valueColumn, empty }: HBarChartProps) {
  const max = Math.max(1, ...items.map((item) => item.value));
  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      series={[{ name: valueColumn, color }]}
      columns={[firstColumn, valueColumn]}
      rows={items.map((item) => ({ key: item.key, label: item.label, values: [fullNumber(item.value)] }))}
    >
      {items.length === 0 ? (
        <p className="m-0 text-sm text-muted">{empty}</p>
      ) : (
        <List label={title} gap="sm">
          {items.map((item) => (
            <ListItem key={item.key} className="grid grid-cols-[minmax(6rem,10rem)_minmax(0,1fr)] items-center gap-2 text-sm">
              <span className="truncate text-muted" title={item.label}>
                {item.label}
              </span>
              <span className="flex min-w-0 items-center gap-2">
                <span
                  aria-hidden="true"
                  className="block h-3 rounded-r-[4px]"
                  style={{ width: `${Math.max(2, (item.value / max) * 85)}%`, background: color }}
                />
                <span className="text-xs font-semibold tabular-nums">{fullNumber(item.value)}</span>
              </span>
            </ListItem>
          ))}
        </List>
      )}
    </ChartFrame>
  );
}
