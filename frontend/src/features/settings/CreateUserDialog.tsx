import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { createUser } from "../../api/client";
import type { CreateUserBody, Role } from "../../api/types";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { useToast } from "../../ui/Toaster";
import { ROLE_OPTIONS, parseRole, roleLabel, settingsErrorText } from "./accountView";
import { INPUT_CLASS, LABEL_CLASS } from "./formStyles";
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
    <form onSubmit={submit} className="grid gap-4">
      <label className={LABEL_CLASS}>
        Username
        <input
          name="username"
          type="text"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      <label className={LABEL_CLASS}>
        Role
        <select
          name="role"
          value={role}
          onChange={(event) => {
            const next = parseRole(event.target.value);
            if (next !== null) {
              setRole(next);
            }
          }}
          className={INPUT_CLASS}
        >
          {ROLE_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {roleLabel(option)}
            </option>
          ))}
        </select>
      </label>
      <label className={LABEL_CLASS}>
        <span>
          Password{" "}
          <span className="font-normal text-muted">
            ({PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters)
          </span>
        </span>
        <input
          name="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      <label className={LABEL_CLASS}>
        Confirm password
        <input
          name="confirm-password"
          type="password"
          autoComplete="new-password"
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      {shownError !== null && (
        <p role="alert" className="m-0 text-sm text-critical">
          {shownError}
        </p>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={mutation.isPending}>
          {mutation.isPending ? "Creating…" : "Create user"}
        </Button>
      </div>
    </form>
  );
}
