import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Card } from "./Card";

describe("Card", () => {
  it("labels the section with its title", () => {
    render(
      <Card title="Needs attention">
        <p>Body</p>
      </Card>,
    );

    expect(screen.getByRole("region", { name: "Needs attention" })).toBeTruthy();
    expect(screen.getByText("Body")).toBeTruthy();
  });

  it("shows hostile title, actions and body as text and creates no element", () => {
    const hostile = "<img src=x onerror=alert(1)>";
    const { container } = render(
      <Card title={hostile} actions={<span>{"<script>alert(1)</script>"}</span>}>
        <p>{hostile}</p>
      </Card>,
    );

    expect(screen.getByRole("heading", { name: hostile })).toBeTruthy();
    expect(screen.getAllByText(hostile)).toHaveLength(2);
    expect(screen.getByText("<script>alert(1)</script>")).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });
});
