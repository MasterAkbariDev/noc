import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { resetUserPassword } from "../../api/client";
import type { UserView } from "../../api/types";
import { Button, Dialog, Field, FieldNote, Form, FormActions, FormMessage, TextInput, useToast } from "../../ui";
import { settingsErrorText } from "./accountView";
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, confirmationProblem, passwordProblem } from "./passwordRules";

type ResetPasswordDialogProps = {
  user: UserView | null;
  onClose: () => void;
};

export function ResetPasswordDialog({ user, onClose }: ResetPasswordDialogProps) {
  return (
    <Dialog
      open={user !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
      title={user === null ? "Reset password" : `Reset the password for ${user.username}`}
      description="Their sessions end at once, so they must sign in again with the new password."
    >
      {user !== null && <ResetPasswordForm user={user} onDone={onClose} />}
    </Dialog>
  );
}

function ResetPasswordForm({ user, onDone }: { user: UserView; onDone: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (newPassword: string) => resetUserPassword(user.id, newPassword),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      toast.success(`Reset the password for ${user.username}. Their sessions ended.`);
      onDone();
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = passwordProblem(password) ?? confirmationProblem(password, confirmation);
    setProblem(found);
    if (found === null) {
      mutation.mutate(password);
    }
  }

  const shownError = problem ?? (mutation.isError ? settingsErrorText(mutation.error) : null);

  return (
    <Form onSubmit={submit}>
      <Field
        label={
          <span>
            New password{" "}
            <FieldNote>({PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters)</FieldNote>
          </span>
        }
      >
        <TextInput
          name="new-password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
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
      <FormActions align="end">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={mutation.isPending}>
          {mutation.isPending ? "Resetting…" : "Reset password"}
        </Button>
      </FormActions>
    </Form>
  );
}
