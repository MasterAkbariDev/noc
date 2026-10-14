import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, totpDisable, totpEnable, totpSetup } from "../../api/client";
import type { MeView } from "../../api/types";
import { useSession } from "../../auth/session";
import { sessionFor } from "./fixtures";
import { renderWithProviders } from "./harness";
import { TwoFactorCard } from "./TwoFactorCard";

vi.mock("../../auth/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../auth/session")>()),
  useSession: vi.fn(),
}));

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  totpSetup: vi.fn(),
  totpEnable: vi.fn(),
  totpDisable: vi.fn(),
}));

const SECRET = "JBSWY3DPEHPK3PXP";
const URI = `otpauth://totp/NOC:alice?secret=${SECRET}`;
const PASSWORD = "correct horse battery";

function signedInAs(extra: Partial<MeView>) {
  const session = sessionFor({ username: "alice", role: "operator", via: "session", ...extra });
  vi.mocked(useSession).mockReturnValue(session);
  return session;
}

beforeEach(() => {
  vi.mocked(useSession).mockReset();
  vi.mocked(totpSetup).mockReset();
  vi.mocked(totpEnable).mockReset();
  vi.mocked(totpDisable).mockReset();
});

afterEach(() => {
  cleanup();
});

describe("TwoFactorCard", () => {
  it("shows that it is off and asks for the password to start", () => {
    signedInAs({ totp_enabled: false });
    renderWithProviders(<TwoFactorCard />);

    expect(screen.getByText("Off")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start setup" })).toBeTruthy();
  });

  it("shows the secret after the password is accepted and then turns it on with a code", async () => {
    signedInAs({ totp_enabled: false });
    vi.mocked(totpSetup).mockResolvedValue({ secret: SECRET, uri: URI });
    vi.mocked(totpEnable).mockResolvedValue(undefined);
    renderWithProviders(<TwoFactorCard />);

    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: PASSWORD } });
    fireEvent.click(screen.getByRole("button", { name: "Start setup" }));

    expect(await screen.findByText(SECRET)).toBeTruthy();
    expect(screen.getByText(URI)).toBeTruthy();
    expect(totpSetup).toHaveBeenCalledWith(PASSWORD);

    fireEvent.change(screen.getByLabelText("Code from the app"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Turn on" }));

    await waitFor(() => expect(totpEnable).toHaveBeenCalledWith("123456"));
    await waitFor(() => expect(screen.queryByText(SECRET)).toBeNull());
  });

  it("shows the server's reason when the password is wrong", async () => {
    signedInAs({ totp_enabled: false });
    vi.mocked(totpSetup).mockRejectedValue(new ApiError(401, "current password is wrong"));
    renderWithProviders(<TwoFactorCard />);

    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "nope" } });
    fireEvent.click(screen.getByRole("button", { name: "Start setup" }));

    expect((await screen.findByRole("alert")).textContent).toBe("current password is wrong");
  });

  it("offers to turn it off when it is on and the role does not require it", async () => {
    const session = signedInAs({ totp_enabled: true, totp_required: false });
    vi.mocked(totpDisable).mockResolvedValue(undefined);
    const logout = vi.fn();
    vi.mocked(useSession).mockReturnValue({ ...session, logout });
    renderWithProviders(<TwoFactorCard />);

    expect(screen.getByText("On")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: PASSWORD } });
    fireEvent.change(screen.getByLabelText("A new code from the app"), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Turn off" }));

    await waitFor(() => expect(totpDisable).toHaveBeenCalledWith(PASSWORD, "654321"));
    await waitFor(() => expect(logout).toHaveBeenCalled());
  });

  it("does not offer to turn it off when the role requires it", () => {
    signedInAs({ totp_enabled: true, totp_required: true });
    renderWithProviders(<TwoFactorCard />);

    expect(screen.queryByRole("button", { name: "Turn off" })).toBeNull();
    expect(screen.getByText(/must use two-factor authentication/)).toBeTruthy();
  });
});
