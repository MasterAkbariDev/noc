import { useId, useState, type ReactNode } from "react";

export type ChartSeries = { name: string; color: string };

export type TableRow = { key: string; label: string; values: string[] };

type ChartFrameProps = {
  title: string;
  subtitle?: string;
  series: ChartSeries[];
  columns: string[];
  rows: TableRow[];
  children: ReactNode;
};

export function ChartFrame({ title, subtitle, series, columns, rows, children }: ChartFrameProps) {
  const titleId = useId();
  const [showTable, setShowTable] = useState(false);
  return (
    <section
      aria-labelledby={titleId}
      className="m-0 grid min-w-0 grid-cols-[minmax(0,1fr)] gap-3 rounded-card border border-border bg-surface p-4 shadow-card"
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="grid gap-0.5">
          <h2 id={titleId} className="m-0 text-base font-semibold">
            {title}
          </h2>
          {subtitle !== undefined && <p className="m-0 text-xs text-muted">{subtitle}</p>}
        </div>
        <button
          type="button"
          className="rounded-control border border-border px-2 py-1 text-xs text-muted hover:bg-surface-2"
          aria-pressed={showTable}
          onClick={() => setShowTable(!showTable)}
        >
          {showTable ? "Show chart" : "Show table"}
        </button>
      </header>
      {series.length >= 2 && (
        <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-xs text-muted" aria-label="Legend">
          {series.map((item) => (
            <li key={item.name} className="flex items-center gap-1.5">
              <span aria-hidden="true" className="inline-block size-2.5 rounded-sm" style={{ background: item.color }} />
              {item.name}
            </li>
          ))}
        </ul>
      )}
      {showTable ? <DataTableView title={title} columns={columns} rows={rows} /> : children}
    </section>
  );
}

function DataTableView({ title, columns, rows }: { title: string; columns: string[]; rows: TableRow[] }) {
  return (
    <div className="max-h-72 overflow-auto">
      <table aria-label={`${title} (table)`} className="w-full text-left text-sm">
        <thead className="text-xs text-muted">
          <tr>
            {columns.map((column) => (
              <th key={column} className="px-2 py-1 font-medium">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-t border-border">
              <td className="px-2 py-1">{row.label}</td>
              {row.values.map((value, index) => (
                <td key={`${row.key}-${index}`} className="px-2 py-1 tabular-nums">
                  {value}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
