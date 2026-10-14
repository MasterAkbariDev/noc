import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { KpiRow } from "./KpiRow";
import { overviewFixture } from "./testData";

function renderRow() {
  return render(
    <MemoryRouter>
      <KpiRow kpis={overviewFixture().kpis} />
    </MemoryRouter>,
  );
}

describe("KpiRow", () => {
  it("shows the four tiles as links to their pages", () => {
    renderRow();

    expect(screen.getByRole("link", { name: /Open incidents/ }).getAttribute("href")).toBe(
      "/incidents?filter=open",
    );
    expect(screen.getByRole("link", { name: /Needs you/ }).getAttribute("href")).toBe(
      "/incidents?filter=needs-you",
    );
    expect(screen.getByRole("link", { name: /Servers/ }).getAttribute("href")).toBe("/servers");
    expect(screen.getByRole("link", { name: /LLM keys/ }).getAttribute("href")).toBe("/system");
  });

  it("shows the counts as text", () => {
    renderRow();

    expect(screen.getByText("2/2")).toBeTruthy();
    expect(screen.getByText("9/10")).toBeTruthy();
  });
});
