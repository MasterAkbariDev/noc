import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Tabs } from "./Tabs";

function Harness({ onChange }: { onChange: (value: string) => void }) {
  const [value, setValue] = useState("evidence");
  return (
    <Tabs
      label="Incident sections"
      value={value}
      onValueChange={(next) => {
        onChange(next);
        setValue(next);
      }}
      items={[
        { value: "evidence", label: "Evidence", content: <p>Evidence body</p> },
        { value: "report", label: "Report", content: <p>Report body</p> },
      ]}
    />
  );
}

describe("Tabs", () => {
  it("shows the content of the selected tab only", () => {
    render(<Harness onChange={() => undefined} />);

    expect(screen.getByText("Evidence body")).toBeTruthy();
    expect(screen.queryByText("Report body")).toBeNull();
    expect(screen.getByRole("tab", { name: "Evidence" }).getAttribute("aria-selected")).toBe("true");
  });

  it("switches the content and reports the new value", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Report" }), { button: 0 });

    expect(onChange).toHaveBeenCalledWith("report");
    expect(screen.getByText("Report body")).toBeTruthy();
    expect(screen.queryByText("Evidence body")).toBeNull();
  });
});
