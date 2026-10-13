import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { UserMenu } from "./UserMenu";

const session = vi.hoisted(() => ({ logout: vi.fn() }));

vi.mock("../auth/session", () => ({
  useSession: () => ({
    me: { username: "alice", role: "operator", via: "session" },
    status: "authenticated",
    logout: session.logout,
  }),
}));

function renderMenu() {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<UserMenu />} />
        <Route path="/settings" element={<p>Settings page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

function openMenu() {
  fireEvent.keyDown(screen.getByRole("button", { name: /alice/ }), { key: "Enter" });
}

afterEach(() => {
  cleanup();
  session.logout.mockReset();
});

describe("UserMenu", () => {
  it("shows the username and the role", () => {
    renderMenu();

    expect(screen.getByRole("button", { name: /alice/ })).toBeTruthy();
    expect(screen.getByText("Operator")).toBeTruthy();
  });

  it("signs out through the session", () => {
    renderMenu();
    openMenu();

    fireEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));

    expect(session.logout).toHaveBeenCalledTimes(1);
  });

  it("opens the account settings page", () => {
    renderMenu();
    openMenu();

    fireEvent.click(screen.getByRole("menuitem", { name: "My account" }));

    expect(screen.getByText("Settings page")).toBeTruthy();
  });
});
