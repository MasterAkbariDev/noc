import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./Button";
import { Dialog } from "./Dialog";

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Open close form</Button>
      <Dialog open={open} onOpenChange={setOpen} title="Mark incident resolved" description="Closing is final.">
        <p>Form body</p>
      </Dialog>
    </>
  );
}

function dialogElement(): HTMLDialogElement {
  const dialog = document.querySelector("dialog");
  if (dialog === null) {
    throw new Error("no dialog rendered");
  }
  return dialog;
}

describe("Dialog", () => {
  it("is closed and renders no body when open is false", () => {
    render(
      <Dialog open={false} onOpenChange={() => undefined} title="Hidden">
        <p>Secret body</p>
      </Dialog>,
    );

    expect(dialogElement().hasAttribute("open")).toBe(false);
    expect(screen.queryByText("Secret body")).toBeNull();
  });

  it("opens as a modal with its title and description", () => {
    render(
      <Dialog open onOpenChange={() => undefined} title="Mark incident resolved" description="Closing is final.">
        <p>Form body</p>
      </Dialog>,
    );

    expect(dialogElement().hasAttribute("open")).toBe(true);
    expect(screen.getByRole("dialog", { name: "Mark incident resolved" })).toBeTruthy();
    expect(screen.getByText("Closing is final.")).toBeTruthy();
    expect(screen.getByText("Form body")).toBeTruthy();
  });

  it("asks to close on Escape and returns focus to the button that opened it", () => {
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open close form" });
    opener.focus();
    fireEvent.click(opener);
    expect(dialogElement().hasAttribute("open")).toBe(true);

    fireEvent(dialogElement(), new Event("cancel", { cancelable: true }));

    expect(dialogElement().hasAttribute("open")).toBe(false);
    expect(document.activeElement).toBe(opener);
  });

  it("calls onOpenChange(false) when the close button is clicked", () => {
    const onOpenChange = vi.fn();
    render(
      <Dialog open onOpenChange={onOpenChange} title="Close">
        <p>Body</p>
      </Dialog>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
