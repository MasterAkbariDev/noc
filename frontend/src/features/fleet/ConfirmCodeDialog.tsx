import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import type { CommandStep } from "../../api/fleet";
import { Button, Dialog, Form, FormActions, FormMessage } from "../../ui";
import { settingsErrorText } from "../settings/accountView";
import { CodeField, StepsList } from "./FleetParts";
import { FLEET_KEY } from "./view";

export type CodeAction = {
  title: string;
  description: string;
  confirmLabel: string;
  danger: boolean;
  doneText: string;
  run: (code: string) => Promise<CommandStep[]>;
};

export function ConfirmCodeDialog({ action, onClose }: { action: CodeAction | null; onClose: () => void }) {
  return (
    <Dialog
      open={action !== null}
      onOpenChange={(open) => !open && onClose()}
      title={action?.title ?? "Confirm"}
      description={action?.description}
    >
      {action !== null && <ConfirmBody action={action} onDone={onClose} />}
    </Dialog>
  );
}

function ConfirmBody({ action, onDone }: { action: CodeAction; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const mutation = useMutation({
    mutationFn: () => action.run(code.trim()),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: [FLEET_KEY] }),
    onError: () => setCode(""),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  if (mutation.isSuccess) {
    return (
      <div className="grid gap-4">
        <p role="status" className="m-0 text-sm">
          {action.doneText}
        </p>
        <StepsList steps={mutation.data} />
        <FormActions align="end">
          <Button variant="primary" onClick={onDone}>
            Done
          </Button>
        </FormActions>
      </div>
    );
  }

  return (
    <Form onSubmit={submit}>
      <CodeField value={code} onChange={setCode} />
      {mutation.isError && <FormMessage>{settingsErrorText(mutation.error)}</FormMessage>}
      <FormActions align="end">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant={action.danger ? "danger" : "primary"} disabled={mutation.isPending}>
          {action.confirmLabel}
        </Button>
      </FormActions>
    </Form>
  );
}
