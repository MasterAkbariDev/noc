import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { KpiTile } from "./KpiTile";

describe("KpiTile", () => {
  it("is a link to its target when it has one", () => {
    render(
      <MemoryRouter>
        <KpiTile label="Servers" value="2/2" hint="all up" tone="ok" to="/servers" />
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: /Servers/ });
    expect(link.getAttribute("href")).toBe("/servers");
    expect(screen.getByText("2/2")).toBeTruthy();
    expect(screen.getByText("all up")).toBeTruthy();
  });

  it("is not a link without a target", () => {
    render(
      <MemoryRouter>
        <KpiTile label="Failed checks" value={0} tone="critical" />
      </MemoryRouter>,
    );

    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("0").closest(".text-critical")).not.toBeNull();
  });
});
