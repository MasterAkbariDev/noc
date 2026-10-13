import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { type Column, DataTable } from "./DataTable";

type Row = { id: string; title: string; target: string };

const COLUMNS: Column<Row>[] = [
  { key: "title", header: "Title", cell: (row) => row.title },
  { key: "target", header: "Target", cell: (row) => row.target },
];

const ROWS: Row[] = [
  { id: "1", title: "Disk almost full", target: "demo-1" },
  { id: "2", title: "Backup late", target: "noc" },
];

describe("DataTable", () => {
  it("renders a real table with column headers and one row per item", () => {
    render(
      <DataTable label="Incidents" columns={COLUMNS} rows={ROWS} rowKey={(row) => row.id} empty="None" />,
    );

    const table = screen.getByRole("table", { name: "Incidents" });
    expect(within(table).getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Title",
      "Target",
    ]);
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(screen.getByText("Backup late")).toBeTruthy();
  });

  it("shows the empty state in a single row spanning every column", () => {
    render(
      <DataTable
        label="Incidents"
        columns={COLUMNS}
        rows={[]}
        rowKey={(row) => row.id}
        empty="No open incidents. All quiet."
      />,
    );

    const cell = screen.getByText("No open incidents. All quiet.");
    expect(cell.tagName).toBe("TD");
    expect(cell.getAttribute("colspan")).toBe("2");
  });

  it("is a focusable scroll region with the label", () => {
    render(<DataTable label="Incidents" columns={COLUMNS} rows={ROWS} rowKey={(row) => row.id} empty="None" />);

    const region = screen.getByRole("region", { name: "Incidents" });
    expect(region.getAttribute("tabindex")).toBe("0");
  });

  it("shows hostile cell text as text and creates no element", () => {
    const hostile = "<img src=x onerror=alert(1)>";
    const { container } = render(
      <DataTable
        label="Incidents"
        columns={COLUMNS}
        rows={[{ id: "9", title: hostile, target: "<script>alert(1)</script>" }]}
        rowKey={(row) => row.id}
        empty="None"
      />,
    );

    expect(screen.getByText(hostile)).toBeTruthy();
    expect(screen.getByText("<script>alert(1)</script>")).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });
});
