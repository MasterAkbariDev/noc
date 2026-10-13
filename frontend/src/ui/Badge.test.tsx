import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Clock } from "lucide-react";
import { Badge } from "./Badge";

describe("Badge", () => {
  it("shows its text with the class of its tone", () => {
    render(<Badge tone="critical">Disk full</Badge>);

    const badge = screen.getByText("Disk full");
    expect(badge.className).toContain("text-critical");
    expect(badge.className).toContain("bg-critical-soft");
  });

  it("renders the icon without a name, next to the text", () => {
    const { container } = render(
      <Badge tone="info" icon={Clock}>
        Waiting
      </Badge>,
    );

    expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByText("Waiting")).toBeTruthy();
  });

  it("shows hostile text as text and creates no element", () => {
    const hostile = "<img src=x onerror=alert(1)>";
    const { container } = render(<Badge tone="warning">{hostile}</Badge>);

    expect(screen.getByText(hostile)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });
});
