import type { ReactNode } from "react";
import { cx } from "../lib/cx";

export type Column<Row> = {
  key: string;
  header: ReactNode;
  cell: (row: Row) => ReactNode;
  className?: string;
  labelOnPhone?: boolean;
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
  stackOnPhone?: boolean;
};

const STACK_CLASS =
  "stack-table max-sm:min-w-0 max-sm:[&_thead]:sr-only max-sm:[&_tbody]:block max-sm:[&_tr]:grid max-sm:[&_tr]:gap-1.5 max-sm:[&_tr]:px-4 max-sm:[&_tr]:py-3 max-sm:[&_td]:block max-sm:[&_td]:p-0";

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
  stackOnPhone = true,
}: DataTableProps<Row>) {
  const cellClass = dense ? "px-2 py-1.5" : "px-4 py-2.5";
  return (
    <div
      role="region"
      aria-label={label}
      tabIndex={0}
      className={cx("m-0 min-w-0 overflow-x-auto", framed && "rounded-card border border-border bg-surface")}
    >
      <table className={cx("m-0 w-full border-collapse text-[15px]", WIDTH_CLASSES[minWidth], stackOnPhone && STACK_CLASS)}>
        <caption className="sr-only">{label}</caption>
        <thead className="text-left text-sm text-muted">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cx("border-b border-border font-medium", cellClass, column.className)}
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
              <tr key={rowKey(row)} className="border-b border-border align-top transition-colors duration-150 last:border-b-0 hover:bg-surface-2/60">
                {columns.map((column) => (
                  <td
                    key={column.key}
                    data-label={stackOnPhone && column.labelOnPhone !== false && typeof column.header === "string" ? column.header : undefined}
                    className={cx(cellClass, column.className)}
                  >
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
