import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Term } from "./Term";
import { TooltipProvider } from "./Tooltip";

function renderTerm(children: string, technical: string) {
  return render(
    <TooltipProvider>
      <Term technical={technical}>{children}</Term>
    </TooltipProvider>,
  );
}

describe("Term", () => {
  it("shows the plain text and is focusable", () => {
    renderTerm("Automatic actions are off", "execution_disabled");

    const term = screen.getByText("Automatic actions are off");
    expect(term.getAttribute("tabindex")).toBe("0");
  });

  it("shows the technical value when focused", async () => {
    renderTerm("Automatic actions are off", "execution_disabled");

    fireEvent.focus(screen.getByText("Automatic actions are off"));

    expect((await screen.findAllByText("execution_disabled")).length).toBeGreaterThan(0);
  });

  it("shows hostile text as text and creates no element", () => {
    const hostile = "<script>alert(1)</script>";
    const { container } = renderTerm(hostile, "raw_code");

    expect(screen.getByText(hostile)).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
  });
});
