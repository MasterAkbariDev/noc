import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActivityFilterBar } from "./ActivityFilterBar";
import { NO_FILTERS } from "./filters";

afterEach(() => {
  cleanup();
});

describe("ActivityFilterBar", () => {
  it("offers every known action and an all-actions choice", () => {
    render(<ActivityFilterBar filters={NO_FILTERS} onChange={vi.fn()} />);

    const select = screen.getByLabelText("Action");
    const options = Array.from(select.querySelectorAll("option")).map((option) => option.textContent);
    expect(options[0]).toBe("All actions");
    expect(options).toContain("Incident closed");
    expect(options).toContain("Failed sign-in");
  });

  it("reports the chosen action with the other filter kept", () => {
    const onChange = vi.fn();
    render(<ActivityFilterBar filters={{ action: "", actor: "bob" }} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("Action"), { target: { value: "login" } });

    expect(onChange).toHaveBeenCalledWith({ action: "login", actor: "bob" });
  });

  it("submits the actor typed in the form, trimmed", () => {
    const onChange = vi.fn();
    render(<ActivityFilterBar filters={NO_FILTERS} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("Who"), { target: { value: "  alice  " } });
    fireEvent.click(screen.getByRole("button", { name: "Filter" }));

    expect(onChange).toHaveBeenCalledWith({ action: "", actor: "alice" });
  });

  it("shows clear filters only when a filter is set, and clears both", () => {
    const onChange = vi.fn();
    const { rerender } = render(<ActivityFilterBar filters={NO_FILTERS} onChange={onChange} />);
    expect(screen.queryByRole("button", { name: "Clear filters" })).toBeNull();

    rerender(<ActivityFilterBar filters={{ action: "login", actor: "bob" }} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(onChange).toHaveBeenCalledWith(NO_FILTERS);
  });
});
