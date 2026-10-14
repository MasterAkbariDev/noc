import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { resetUserPassword } from "../../api/client";
import type { UserView } from "../../api/types";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { useToast } from "../../ui/Toaster";
import { settingsErrorText } from "./accountView";
import { INPUT_CLASS, LABEL_CLASS } from "./formStyles";
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
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      toast.success(`Reset the password for ${updated.username}. Their sessions ended.`);
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
    <form onSubmit={submit} className="grid gap-4">
      <label className={LABEL_CLASS}>
        <span>
          New password{" "}
          <span className="font-normal text-muted">
            ({PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters)
          </span>
        </span>
        <input
          name="new-password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      <label className={LABEL_CLASS}>
        Confirm new password
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
          {mutation.isPending ? "Resetting…" : "Reset password"}
        </Button>
      </div>
    </form>
  );
}
