import { ChartColumn, Table2 } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { cx } from "../../lib/cx";
import { Button } from "../Button";
import { DataTable } from "../DataTable";
import { List, ListItem } from "../List";

export type ChartSeries = { name: string; color: string };
export type TableRow = { key: string; label: string; values: string[] };

type ChartFrameProps = {
  title: string;
  subtitle?: string;
  series: ChartSeries[];
  columns: string[];
  rows: TableRow[];
  children: ReactNode;
  className?: string;
};

export function Swatch({ color }: { color: string }) {
  return <span aria-hidden="true" className="inline-block size-2.5 shrink-0 rounded-sm" style={{ background: color }} />;
}

export function ChartFrame({ title, subtitle, series, columns, rows, children, className }: ChartFrameProps) {
  const titleId = useId();
  const [showTable, setShowTable] = useState(false);
  return (
    <section
      aria-labelledby={titleId}
      className={cx(
        "m-0 grid min-w-0 grid-cols-[minmax(0,1fr)] content-start gap-3 rounded-card border border-border bg-surface p-5 shadow-card",
        className,
      )}
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="grid gap-0.5">
          <h2 id={titleId} className="m-0 text-base font-semibold">
            {title}
          </h2>
          {subtitle !== undefined && <p className="m-0 text-xs text-muted">{subtitle}</p>}
        </div>
        <Button variant="ghost" size="sm" className="text-xs text-muted" aria-pressed={showTable} onClick={() => setShowTable(!showTable)}>
          {showTable ? <ChartColumn aria-hidden="true" size={14} /> : <Table2 aria-hidden="true" size={14} />}
          {showTable ? "Show chart" : "Show table"}
        </Button>
      </header>
      {series.length >= 2 && (
        <List label="Legend" variant="inline" gap="xs" className="gap-x-4 text-xs text-muted">
          {series.map((item) => (
            <ListItem key={item.name} className="flex items-center gap-1.5">
              <Swatch color={item.color} />
              {item.name}
            </ListItem>
          ))}
        </List>
      )}
      {showTable ? (
        <DataTable
          label={`${title} (table)`}
          columns={columns.map((column, index) => ({
            key: column,
            header: column,
            className: index === 0 ? undefined : "tabular-nums",
            cell: (row: TableRow) => (index === 0 ? row.label : row.values[index - 1]),
          }))}
          rows={rows}
          rowKey={(row) => row.key}
          empty="No data."
          framed={false}
          dense
          minWidth="none"
        />
      ) : (
        children
      )}
    </section>
  );
}
