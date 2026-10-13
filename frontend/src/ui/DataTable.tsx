import type { ReactNode } from "react";
import { cx } from "../lib/cx";

export type Column<Row> = {
  key: string;
  header: ReactNode;
  cell: (row: Row) => ReactNode;
  className?: string;
};

type DataTableProps<Row> = {
  label: string;
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  empty: ReactNode;
};

export function DataTable<Row>({ label, columns, rows, rowKey, empty }: DataTableProps<Row>) {
  return (
    <div
      role="region"
      aria-label={label}
      tabIndex={0}
      className="m-0 overflow-x-auto rounded-card border border-border bg-surface"
    >
      <table className="m-0 w-full min-w-[32rem] border-collapse text-sm">
        <caption className="sr-only">{label}</caption>
        <thead className="bg-surface-2 text-left text-muted">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cx("border-b border-border px-3 py-2 font-semibold", column.className)}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-6 text-center text-muted">
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={rowKey(row)} className="border-b border-border align-top last:border-b-0">
                {columns.map((column) => (
                  <td key={column.key} className={cx("px-3 py-2", column.className)}>
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
