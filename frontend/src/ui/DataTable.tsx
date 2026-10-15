import type { ReactNode } from "react";
import { cx } from "../lib/cx";

export type Column<Row> = {
  key: string;
  header: ReactNode;
  cell: (row: Row) => ReactNode;
  className?: string;
};

export type FooterCell = { key: string; content: ReactNode; span?: number };

export type TableWidth = "none" | "sm" | "md" | "lg";

const WIDTH_CLASSES: Record<TableWidth, string> = {
  none: "",
  sm: "min-w-[22rem]",
  md: "min-w-[32rem]",
  lg: "min-w-[40rem]",
};

type DataTableProps<Row> = {
  label: string;
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  empty: ReactNode;
  footer?: FooterCell[];
  framed?: boolean;
  dense?: boolean;
  minWidth?: TableWidth;
};

export function DataTable<Row>({
  label,
  columns,
  rows,
  rowKey,
  empty,
  footer,
  framed = true,
  dense = false,
  minWidth = "md",
}: DataTableProps<Row>) {
  const cellClass = dense ? "px-2 py-1.5" : "px-4 py-2.5";
  return (
    <div
      role="region"
      aria-label={label}
      tabIndex={0}
      className={cx("m-0 min-w-0 overflow-x-auto", framed && "rounded-card border border-border bg-surface shadow-card")}
    >
      <table className={cx("m-0 w-full border-collapse text-sm", WIDTH_CLASSES[minWidth])}>
        <caption className="sr-only">{label}</caption>
        <thead className="bg-surface-2 text-left text-xs tracking-wide text-muted uppercase">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cx("border-b border-border font-semibold", cellClass, column.className)}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-muted">
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={rowKey(row)} className="border-b border-border align-top transition-colors last:border-b-0 hover:bg-surface-2/60">
                {columns.map((column) => (
                  <td key={column.key} className={cx(cellClass, column.className)}>
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
        {footer !== undefined && rows.length > 0 && (
          <tfoot className="border-t border-border bg-surface-2 font-medium">
            <tr>
              {footer.map((cell, index) =>
                index === 0 ? (
                  <th key={cell.key} scope="row" colSpan={cell.span} className={cx("text-left font-semibold", cellClass)}>
                    {cell.content}
                  </th>
                ) : (
                  <td key={cell.key} colSpan={cell.span} className={cellClass}>
                    {cell.content}
                  </td>
                ),
              )}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
