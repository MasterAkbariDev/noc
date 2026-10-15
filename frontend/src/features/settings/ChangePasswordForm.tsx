import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { changePassword } from "../../api/client";
import { Button, Field, FieldNote, Form, FormActions, FormMessage, TextInput, useToast } from "../../ui";
import { settingsErrorText } from "./accountView";
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, confirmationProblem, passwordProblem } from "./passwordRules";

type ChangeRequest = { currentPassword: string; newPassword: string };

export function ChangePasswordForm() {
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: ({ currentPassword, newPassword }: ChangeRequest) => changePassword(currentPassword, newPassword),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setConfirmation("");
      toast.success("Password changed. Your other sessions are signed out.");
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = currentProblem(current) ?? passwordProblem(next) ?? confirmationProblem(next, confirmation);
    setProblem(found);
    if (found === null) {
      mutation.mutate({ currentPassword: current, newPassword: next });
    }
  }

  const shownError = problem ?? (mutation.isError ? settingsErrorText(mutation.error) : null);

  return (
    <Form width="narrow" onSubmit={submit}>
      <h3 className="m-0 text-base font-semibold">Change password</h3>
      <p className="m-0 text-sm text-muted">
        Changing your password signs out your other sessions. This browser stays signed in.
      </p>
      <Field label="Current password">
        <TextInput
          name="current-password"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
        />
      </Field>
      <Field
        label={
          <span>
            New password{" "}
            <FieldNote>
              ({PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters)
            </FieldNote>
          </span>
        }
      >
        <TextInput
          name="new-password"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(event) => setNext(event.target.value)}
        />
      </Field>
      <Field label="Confirm new password">
        <TextInput
          name="confirm-password"
          type="password"
          autoComplete="new-password"
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
        />
      </Field>
      {shownError !== null && <FormMessage>{shownError}</FormMessage>}
      <FormActions>
        <Button type="submit" variant="primary" disabled={mutation.isPending}>
          {mutation.isPending ? "Changing…" : "Change password"}
        </Button>
      </FormActions>
    </Form>
  );
}

function currentProblem(current: string): string | null {
  return current === "" ? "Enter your current password." : null;
}
