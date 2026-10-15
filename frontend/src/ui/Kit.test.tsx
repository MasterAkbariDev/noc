import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { Bell, Sun } from "lucide-react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Alert } from "./Alert";
import { Avatar, initials } from "./Avatar";
import { IconButton } from "./IconButton";
import { DescriptionList, List, ListItem } from "./List";
import { Meter } from "./Meter";
import { SegmentedControl } from "./SegmentedControl";

afterEach(() => {
  cleanup();
});

describe("SegmentedControl", () => {
  it("presses only the chosen segment and reports a new choice", () => {
    const onChange = vi.fn();
    render(
      <SegmentedControl
        label="Show"
        value="open"
        onChange={onChange}
        segments={[
          { value: "open", label: "Open" },
          { value: "all", label: "All" },
        ]}
      />,
    );

    const group = screen.getByRole("group", { name: "Show" });
    expect(within(group).getByRole("button", { name: "Open" }).getAttribute("aria-pressed")).toBe("true");
    expect(within(group).getByRole("button", { name: "All" }).getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(onChange).toHaveBeenCalledWith("all");
  });

  it("keeps the label as the name when only icons are shown", () => {
    render(
      <SegmentedControl label="Theme" iconOnly value="light" onChange={vi.fn()} segments={[{ value: "light", label: "Light", icon: Sun }]} />,
    );

    expect(screen.getByRole("button", { name: "Light" }).textContent).toBe("");
  });
});

describe("List", () => {
  it("renders an ordered list only when asked", () => {
    const { container, rerender } = render(
      <List label="Steps">
        <ListItem>One</ListItem>
      </List>,
    );
    expect(container.querySelector("ul")).not.toBeNull();

    rerender(
      <List label="Steps" ordered>
        <ListItem>One</ListItem>
      </List>,
    );
    expect(container.querySelector("ol")).not.toBeNull();
    expect(screen.getByRole("list", { name: "Steps" })).toBeTruthy();
  });

  it("pairs every term with its detail", () => {
    render(
      <DescriptionList
        items={[
          { key: "a", term: "Username", detail: "alice" },
          { key: "b", term: "Role", detail: "Admin" },
        ]}
      />,
    );

    expect(screen.getAllByRole("term").map((term) => term.textContent)).toEqual(["Username", "Role"]);
    expect(screen.getAllByRole("definition").map((detail) => detail.textContent)).toEqual(["alice", "Admin"]);
  });
});

describe("Meter", () => {
  it("clamps the value and reads out its text", () => {
    render(<Meter label="Disk" value={140} valueText="140%" />);

    const meter = screen.getByRole("meter", { name: "Disk" });
    expect(meter.getAttribute("aria-valuenow")).toBe("100");
    expect(meter.getAttribute("aria-valuetext")).toBe("140%");
  });
});

describe("Alert", () => {
  it("is a labelled region with its title, body and action", () => {
    render(
      <Alert tone="warning" label="Overall status" title="1 incident needs you" action={<button type="button">Open</button>}>
        <p>Details</p>
      </Alert>,
    );

    const region = screen.getByRole("region", { name: "Overall status" });
    expect(within(region).getByText("1 incident needs you")).toBeTruthy();
    expect(within(region).getByRole("button", { name: "Open" })).toBeTruthy();
  });
});

describe("IconButton", () => {
  it("names an icon-only button by its label", () => {
    const onClick = vi.fn();
    render(<IconButton label="Notifications" icon={Bell} onClick={onClick} />);

    fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe("Avatar", () => {
  it("shows up to two initials and hides itself from screen readers", () => {
    expect(initials("alice")).toBe("AL");
    expect(initials("e2e-admin")).toBe("EA");
    expect(initials("Ada Byron Lovelace")).toBe("AB");
    const { container } = render(<Avatar name="alice" />);
    expect(container.firstElementChild?.getAttribute("aria-hidden")).toBe("true");
  });
});
