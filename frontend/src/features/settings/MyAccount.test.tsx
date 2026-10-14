import { cleanup, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSession } from "../../auth/session";
import { HOSTILE_USERNAME, sessionFor } from "./fixtures";
import { renderWithProviders } from "./harness";
import { MyAccount } from "./MyAccount";

vi.mock("../../auth/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../auth/session")>()),
  useSession: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(useSession).mockReset();
});

afterEach(() => {
  cleanup();
});

describe("MyAccount", () => {
  it("shows the signed-in username and the role in words", () => {
    vi.mocked(useSession).mockReturnValue(sessionFor({ username: "alice", role: "operator", via: "session" }));
    renderWithProviders(<MyAccount />);

    expect(screen.getByText("alice")).toBeTruthy();
    expect(screen.getByText("Operator")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Change password" })).toBeTruthy();
  });

  it("shows a hostile username as text and creates no element", () => {
    vi.mocked(useSession).mockReturnValue(sessionFor({ username: HOSTILE_USERNAME, role: "viewer", via: "session" }));
    renderWithProviders(<MyAccount />);

    expect(screen.getByText(HOSTILE_USERNAME)).toBeTruthy();
    expect(document.querySelector("img")).toBeNull();
  });
});
