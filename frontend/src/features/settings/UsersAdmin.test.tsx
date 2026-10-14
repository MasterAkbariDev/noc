import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  disableUser,
  enableUser,
  getUsers,
  resetUserPassword,
  setUserRole,
} from "../../api/client";
import { useSession } from "../../auth/session";
import { OWN_ACCOUNT_REASON, OWN_ROLE_REASON } from "./accountView";
import { HOSTILE_USERNAME, sessionFor, userFixture } from "./fixtures";
import { renderWithProviders } from "./harness";
import { UsersAdmin } from "./UsersAdmin";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getUsers: vi.fn(),
  setUserRole: vi.fn(),
  disableUser: vi.fn(),
  enableUser: vi.fn(),
  resetUserPassword: vi.fn(),
}));

vi.mock("../../auth/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../auth/session")>()),
  useSession: vi.fn(),
}));

const ALICE = userFixture({ id: "u-alice", username: "alice", role: "viewer" });
const BOB = userFixture({
  id: "u-bob",
  username: "bob",
  role: "operator",
  disabled: true,
  last_login_at: "2026-10-10T09:00:00Z",
});
const ADMIN_ROW = userFixture({ id: "u-admin", username: "admin", role: "admin" });

function renderAs(role: "viewer" | "operator" | "admin", username = "admin") {
  vi.mocked(useSession).mockReturnValue(sessionFor({ username, role, via: "session" }));
  return renderWithProviders(<UsersAdmin />);
}

function rowFor(username: string): HTMLElement {
  const row = screen
    .getAllByRole("row")
    .find((candidate) => candidate.querySelector("td")?.textContent?.startsWith(username));
  if (row === undefined) {
    throw new Error(`no row for ${username}`);
  }
  return row;
}

function dialogNamed(name: string): HTMLElement {
  return screen.getByRole("dialog", { name });
}

beforeEach(() => {
  vi.mocked(getUsers).mockReset();
  vi.mocked(setUserRole).mockReset();
  vi.mocked(disableUser).mockReset();
  vi.mocked(enableUser).mockReset();
  vi.mocked(resetUserPassword).mockReset();
  vi.mocked(useSession).mockReset();
});

afterEach(() => {
  cleanup();
});

describe("UsersAdmin visibility", () => {
  it.each(["viewer", "operator"] as const)("is hidden for a %s and never asks for the user list", (role) => {
    renderAs(role);

    expect(screen.queryByRole("heading", { name: "Users" })).toBeNull();
    expect(getUsers).not.toHaveBeenCalled();
  });

  it("is shown to an admin with the list", async () => {
    vi.mocked(getUsers).mockResolvedValue([ADMIN_ROW, ALICE, BOB]);
    renderAs("admin");

    expect(await screen.findByRole("heading", { name: "Users" })).toBeTruthy();
    expect(await screen.findByRole("table", { name: "Users" })).toBeTruthy();
    expect(getUsers).toHaveBeenCalledTimes(1);
  });
});

describe("UsersAdmin table", () => {
  it("shows each user's role, status and last login", async () => {
    vi.mocked(getUsers).mockResolvedValue([ALICE, BOB]);
    renderAs("admin");

    await screen.findByRole("table", { name: "Users" });

    expect((screen.getByRole("combobox", { name: "Role for alice" }) as HTMLSelectElement).value).toBe("viewer");
    expect(within(rowFor("bob")).getByText("Disabled")).toBeTruthy();
    expect(within(rowFor("alice")).getByText("Active")).toBeTruthy();
    expect(within(rowFor("alice")).getByText("Never")).toBeTruthy();
    expect(within(rowFor("bob")).getByRole("button", { name: "Enable" })).toBeTruthy();
  });

  it("locks the role select and the actions on the admin's own row, with the reason", async () => {
    vi.mocked(getUsers).mockResolvedValue([ADMIN_ROW, ALICE]);
    renderAs("admin", "admin");

    await screen.findByRole("table", { name: "Users" });
    const own = rowFor("admin");

    expect((within(own).getByRole("combobox", { name: "Role for admin" }) as HTMLSelectElement).disabled).toBe(true);
    expect(within(own).getByRole("button", { name: "Disable" }).hasAttribute("disabled")).toBe(true);
    expect(within(own).getByRole("button", { name: "Reset password" }).hasAttribute("disabled")).toBe(true);
    expect(within(own).getByText(OWN_ROLE_REASON)).toBeTruthy();
    expect(within(own).getByText(OWN_ACCOUNT_REASON)).toBeTruthy();
    expect(within(rowFor("alice")).getByRole("button", { name: "Disable" }).hasAttribute("disabled")).toBe(false);
  });

  it("renders a hostile username as text and creates no element", async () => {
    vi.mocked(getUsers).mockResolvedValue([userFixture({ id: "u-x", username: HOSTILE_USERNAME })]);
    renderAs("admin");

    expect(await screen.findByText(HOSTILE_USERNAME)).toBeTruthy();
    expect(document.querySelector("img")).toBeNull();
  });

  it("shows the empty text when there are no users", async () => {
    vi.mocked(getUsers).mockResolvedValue([]);
    renderAs("admin");

    expect(await screen.findByText("No users yet.")).toBeTruthy();
  });

  it("offers a retry when the list cannot be loaded", async () => {
    vi.mocked(getUsers).mockRejectedValueOnce(new ApiError(500, "database is busy"));
    vi.mocked(getUsers).mockResolvedValueOnce([ALICE]);
    renderAs("admin");

    expect(await screen.findByText("database is busy")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("table", { name: "Users" })).toBeTruthy();
  });
});

describe("UsersAdmin actions", () => {
  it("changes a role from the select and confirms with a toast", async () => {
    vi.mocked(getUsers).mockResolvedValue([ALICE]);
    vi.mocked(setUserRole).mockResolvedValue({ ...ALICE, role: "operator" });
    renderAs("admin");

    await screen.findByRole("table", { name: "Users" });
    fireEvent.change(screen.getByRole("combobox", { name: "Role for alice" }), { target: { value: "operator" } });

    expect(await screen.findByText("Changed alice to Operator.")).toBeTruthy();
    expect(setUserRole).toHaveBeenCalledWith("u-alice", "operator");
  });

  it("asks before disabling, then disables and says the sessions ended", async () => {
    vi.mocked(getUsers).mockResolvedValue([ALICE]);
    vi.mocked(disableUser).mockResolvedValue({ ...ALICE, disabled: true });
    renderAs("admin");

    await screen.findByRole("table", { name: "Users" });
    fireEvent.click(within(rowFor("alice")).getByRole("button", { name: "Disable" }));

    const dialog = dialogNamed("Disable alice?");
    expect(disableUser).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Disable account" }));

    expect(await screen.findByText("Disabled alice. Their sessions ended.")).toBeTruthy();
    expect(disableUser).toHaveBeenCalledWith("u-alice");
  });

  it("asks before enabling a disabled user", async () => {
    vi.mocked(getUsers).mockResolvedValue([BOB]);
    vi.mocked(enableUser).mockResolvedValue({ ...BOB, disabled: false });
    renderAs("admin");

    await screen.findByRole("table", { name: "Users" });
    fireEvent.click(within(rowFor("bob")).getByRole("button", { name: "Enable" }));
    fireEvent.click(within(dialogNamed("Enable bob?")).getByRole("button", { name: "Enable account" }));

    expect(await screen.findByText("Enabled bob.")).toBeTruthy();
    expect(enableUser).toHaveBeenCalledWith("u-bob");
  });

  it("shows the server's 409 text inside the confirmation and keeps it open", async () => {
    vi.mocked(getUsers).mockResolvedValue([ALICE]);
    vi.mocked(disableUser).mockRejectedValue(new ApiError(409, "cannot disable the last active admin"));
    renderAs("admin");

    await screen.findByRole("table", { name: "Users" });
    fireEvent.click(within(rowFor("alice")).getByRole("button", { name: "Disable" }));
    fireEvent.click(within(dialogNamed("Disable alice?")).getByRole("button", { name: "Disable account" }));

    const alert = await within(dialogNamed("Disable alice?")).findByRole("alert");
    expect(alert.textContent).toBe("cannot disable the last active admin");
  });

  it("resets a password from the dialog and confirms with a toast", async () => {
    vi.mocked(getUsers).mockResolvedValue([ALICE]);
    vi.mocked(resetUserPassword).mockResolvedValue(ALICE);
    renderAs("admin");

    await screen.findByRole("table", { name: "Users" });
    fireEvent.click(within(rowFor("alice")).getByRole("button", { name: "Reset password" }));

    const dialog = dialogNamed("Reset the password for alice");
    fireEvent.change(within(dialog).getByLabelText(/^New password/), { target: { value: "fresh-password-123" } });
    fireEvent.change(within(dialog).getByLabelText("Confirm new password"), {
      target: { value: "fresh-password-123" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Reset password" }));

    expect(await screen.findByText("Reset the password for alice. Their sessions ended.")).toBeTruthy();
    expect(resetUserPassword).toHaveBeenCalledWith("u-alice", "fresh-password-123");
  });
});
