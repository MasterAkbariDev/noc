import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, createUser } from "../../api/client";
import { CreateUserDialog } from "./CreateUserDialog";
import { userFixture } from "./fixtures";
import { renderWithProviders } from "./harness";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  createUser: vi.fn(),
}));

const PASSWORD = "correct-horse-battery";

function renderOpen() {
  return renderWithProviders(<CreateUserDialog open onOpenChange={() => undefined} />);
}

function dialog(): HTMLElement {
  return screen.getByRole("dialog", { name: "Create user" });
}

function fillForm(username: string, password: string, confirmation: string) {
  const scope = within(dialog());
  fireEvent.change(scope.getByLabelText("Username"), { target: { value: username } });
  fireEvent.change(scope.getByLabelText(/^Password/), { target: { value: password } });
  fireEvent.change(scope.getByLabelText("Confirm password"), { target: { value: confirmation } });
}

function submit() {
  fireEvent.click(within(dialog()).getByRole("button", { name: "Create user" }));
}

beforeEach(() => {
  vi.mocked(createUser).mockReset();
});

afterEach(() => {
  cleanup();
});

describe("CreateUserDialog", () => {
  it("blocks submit when the two passwords differ", () => {
    renderOpen();

    fillForm("ops.team", PASSWORD, "correct-horse-batteryx");
    submit();

    expect(within(dialog()).getByRole("alert").textContent).toBe("The two passwords do not match.");
    expect(createUser).not.toHaveBeenCalled();
  });

  it("sends the trimmed, lower-case username with the chosen role", async () => {
    vi.mocked(createUser).mockResolvedValue(userFixture({ username: "ops.team", role: "viewer" }));
    renderOpen();

    fillForm("  Ops.Team  ", PASSWORD, PASSWORD);
    submit();

    await screen.findByText("Created ops.team.");
    expect(createUser).toHaveBeenCalledWith({ username: "ops.team", password: PASSWORD, role: "viewer" });
  });

  it("shows the 409 text inline when the username is taken", async () => {
    vi.mocked(createUser).mockRejectedValue(new ApiError(409, "username already exists"));
    renderOpen();

    fillForm("alice", PASSWORD, PASSWORD);
    submit();

    expect((await within(dialog()).findByRole("alert")).textContent).toBe("username already exists");
  });
});
