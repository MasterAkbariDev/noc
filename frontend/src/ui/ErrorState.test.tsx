import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorState } from "./ErrorState";

describe("ErrorState", () => {
  it("shows the title and message as an alert", () => {
    render(<ErrorState title="Could not load incidents" message="The NOC API did not answer." />);

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Could not load incidents");
    expect(alert.textContent).toContain("The NOC API did not answer.");
  });

  it("calls onRetry when Try again is clicked", () => {
    const onRetry = vi.fn();
    render(<ErrorState title="Failed" message="Timeout" onRetry={onRetry} />);

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("has no retry button without onRetry", () => {
    render(<ErrorState title="Failed" message="Timeout" />);

    expect(screen.queryByRole("button")).toBeNull();
  });
});
