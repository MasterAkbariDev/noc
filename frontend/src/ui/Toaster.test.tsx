import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Button } from "./Button";
import { Toaster, useToast } from "./Toaster";

function Saver() {
  const toast = useToast();
  return (
    <>
      <Button onClick={() => toast.success("Saved the change.")}>Save</Button>
      <Button onClick={() => toast.error("Could not save.")}>Fail</Button>
    </>
  );
}

function HostileToast({ message }: { message: string }) {
  const toast = useToast();
  return <Button onClick={() => toast.success(message)}>Show hostile</Button>;
}

describe("Toaster", () => {
  it("shows a success message after useToast().success", async () => {
    render(
      <Toaster>
        <Saver />
      </Toaster>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Saved the change.")).toBeTruthy();
  });

  it("shows an error message in the notifications region", async () => {
    render(
      <Toaster>
        <Saver />
      </Toaster>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Fail" }));

    const region = await screen.findByRole("region", { name: /notifications/i });
    expect(within(region).getByText("Could not save.")).toBeTruthy();
  });

  it("shows hostile message text as text and creates no element", async () => {
    const hostile = "<img src=x onerror=alert(1)>";
    render(
      <Toaster>
        <HostileToast message={hostile} />
      </Toaster>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Show hostile" }));

    expect(await screen.findByText(hostile)).toBeTruthy();
    expect(document.querySelector("img")).toBeNull();
  });
});
