import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { createUser } from "../../api/client";
import type { CreateUserBody, Role } from "../../api/types";
import { Button, Dialog, Field, FieldNote, Form, FormActions, FormMessage, Select, TextInput } from "../../ui";
import { useToast } from "../../ui/Toaster";
import { ROLE_OPTIONS, parseRole, roleLabel, settingsErrorText } from "./accountView";
import {
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  confirmationProblem,
  normalizeUsername,
  passwordProblem,
  usernameProblem,
} from "./passwordRules";

type CreateUserDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function CreateUserDialog({ open, onOpenChange }: CreateUserDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Create user"
      description="The new person signs in with this username and password. Share the password through a channel you trust."
    >
      <CreateUserForm onDone={() => onOpenChange(false)} />
    </Dialog>
  );
}

function CreateUserForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (body: CreateUserBody) => createUser(body),
    onSuccess: (user) => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      toast.success(`Created ${user.username}.`);
      onDone();
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = usernameProblem(username) ?? passwordProblem(password) ?? confirmationProblem(password, confirmation);
    setProblem(found);
    if (found === null) {
      mutation.mutate({ username: normalizeUsername(username), password, role });
    }
  }

  const shownError = problem ?? (mutation.isError ? settingsErrorText(mutation.error) : null);

  return (
    <Form onSubmit={submit}>
      <Field label="Username">
        <TextInput
          name="username"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          value={username}
          onChange={(event) => setUsername(event.target.value)}
        />
      </Field>
      <Field label="Role">
        <Select
          name="role"
          value={role}
          options={ROLE_OPTIONS.map((option) => ({ value: option, label: roleLabel(option) }))}
          onChange={(event) => {
            const next = parseRole(event.target.value);
            if (next !== null) {
              setRole(next);
            }
          }}
        />
      </Field>
      <Field
        label={
          <span>
            Password{" "}
            <FieldNote>
              ({PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters)
            </FieldNote>
          </span>
        }
      >
        <TextInput
          name="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </Field>
      <Field label="Confirm password">
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
          {mutation.isPending ? "Creating…" : "Create user"}
        </Button>
      </FormActions>
    </Form>
  );
}
