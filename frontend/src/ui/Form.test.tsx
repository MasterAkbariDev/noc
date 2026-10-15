import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Checkbox, Field, FieldNote, Form, FormMessage, Select, TextArea, TextInput } from "./Form";

afterEach(() => {
  cleanup();
});

describe("Form controls", () => {
  it("names each control by the label of its field", () => {
    render(
      <Form>
        <Field label="Username">
          <TextInput name="username" />
        </Field>
        <Field label="Note" hint="Shown to everyone">
          <TextArea />
        </Field>
      </Form>,
    );

    expect(screen.getByRole("textbox", { name: "Username" }).getAttribute("type")).toBe("text");
    expect(screen.getByText("Shown to everyone")).toBeTruthy();
    expect(screen.getByLabelText(/Note/).tagName).toBe("TEXTAREA");
  });

  it("keeps a field note inside the label", () => {
    render(
      <Field
        label={
          <span>
            Password <FieldNote>(12 to 128 characters)</FieldNote>
          </span>
        }
      >
        <TextInput type="password" />
      </Field>,
    );

    expect(screen.getByLabelText("Password (12 to 128 characters)")).toBeTruthy();
  });

  it("lists the options of a select and reports the one picked", () => {
    const onChange = vi.fn();
    render(
      <Field label="Role">
        <Select
          value="viewer"
          onChange={(event) => onChange(event.target.value)}
          options={[
            { value: "viewer", label: "Viewer" },
            { value: "admin", label: "Admin" },
          ]}
        />
      </Field>,
    );

    const select = screen.getByLabelText("Role") as HTMLSelectElement;
    expect(Array.from(select.options).map((option) => option.textContent)).toEqual(["Viewer", "Admin"]);
    fireEvent.change(select, { target: { value: "admin" } });
    expect(onChange).toHaveBeenCalledWith("admin");
  });

  it("toggles a checkbox through its label", () => {
    const onChange = vi.fn();
    render(<Checkbox label="I checked this incident" checked={false} onChange={(event) => onChange(event.target.checked)} />);

    fireEvent.click(screen.getByLabelText("I checked this incident"));

    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("announces an error as an alert and a success as a status", () => {
    const { rerender } = render(<FormMessage>Wrong password.</FormMessage>);
    expect(screen.getByRole("alert").textContent).toBe("Wrong password.");

    rerender(<FormMessage tone="ok">Saved.</FormMessage>);
    expect(screen.getByRole("status").textContent).toBe("Saved.");
  });
});
