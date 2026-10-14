import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, changePassword } from "../../api/client";
import { ChangePasswordForm } from "./ChangePasswordForm";
import { renderWithProviders } from "./harness";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  changePassword: vi.fn(),
}));

const CURRENT = "current-password-1";
const NEXT = "brand-new-password-2";

function fill(current: string, next: string, confirmation: string) {
  fireEvent.change(screen.getByLabelText(/^Current password/), { target: { value: current } });
  fireEvent.change(screen.getByLabelText(/^New password/), { target: { value: next } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: confirmation } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));
}

beforeEach(() => {
  vi.mocked(changePassword).mockReset();
});

afterEach(() => {
  cleanup();
});

describe("ChangePasswordForm", () => {
  it("blocks submit when the confirmation does not match", () => {
    renderWithProviders(<ChangePasswordForm />);

    fill(CURRENT, NEXT, "something-else-3");
    submit();

    expect(screen.getByRole("alert").textContent).toBe("The two passwords do not match.");
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("blocks a new password outside 12 to 128 characters", () => {
    renderWithProviders(<ChangePasswordForm />);

    fill(CURRENT, "short", "short");
    submit();

    expect(screen.getByRole("alert").textContent).toBe("Use 12 to 128 characters.");
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("asks for the current password before anything else", () => {
    renderWithProviders(<ChangePasswordForm />);

    fill("", NEXT, NEXT);
    submit();

    expect(screen.getByRole("alert").textContent).toBe("Enter your current password.");
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("sends the change, clears the fields and says the other sessions are signed out", async () => {
    vi.mocked(changePassword).mockResolvedValue(undefined);
    renderWithProviders(<ChangePasswordForm />);

    fill(CURRENT, NEXT, NEXT);
    submit();

    expect(await screen.findByText("Password changed. Your other sessions are signed out.")).toBeTruthy();
    expect(changePassword).toHaveBeenCalledWith(CURRENT, NEXT);
    await waitFor(() =>
      expect((screen.getByLabelText(/^Current password/) as HTMLInputElement).value).toBe(""),
    );
  });

  it("shows the server's detail when the current password is wrong", async () => {
    vi.mocked(changePassword).mockRejectedValue(new ApiError(401, "current password is wrong"));
    renderWithProviders(<ChangePasswordForm />);

    fill(CURRENT, NEXT, NEXT);
    submit();

    expect((await screen.findByRole("alert")).textContent).toBe("current password is wrong");
  });
});
