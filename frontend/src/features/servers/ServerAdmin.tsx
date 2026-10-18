import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { setServerAutomation, setServerLabel, setServerTag } from "../../api/client";
import type { ServerSummary } from "../../api/types";
import { useSession } from "../../auth/session";
import { Button } from "../../ui/Button";
import { Field, Select, TextInput } from "../../ui/Form";
import { useToast } from "../../ui/Toaster";
import { settingsErrorText } from "../settings/accountView";

export const MODE_OPTIONS = [
  { value: "auto_safe", label: "Safe: fixes run automatically" },
  { value: "approval_required", label: "Accept: fixes wait for your approval" },
  { value: "observe_only", label: "Observe only: report, never fix" },
];

export function ServerAdmin({ server }: { server: ServerSummary }) {
  const { me } = useSession();
  if (me.role !== "admin") {
    return null;
  }
  return <AdminControls server={server} />;
}

function AdminControls({ server }: { server: ServerSummary }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [label, setLabel] = useState(server.label ?? "");
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["servers"] });
    void queryClient.invalidateQueries({ queryKey: ["server", server.id] });
  };
  const mode = useMutation({
    mutationFn: (level: string) => setServerAutomation(server.name, level),
    onSuccess: () => {
      refresh();
      toast.success(`Mode of ${server.name} saved.`);
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });
  const tag = useMutation({
    mutationFn: (value: string) => setServerTag(server.name, value === "" ? null : value),
    onSuccess: () => {
      refresh();
      toast.success(`Tag of ${server.name} saved.`);
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });
  const name = useMutation({
    mutationFn: () => setServerLabel(server.name, label.trim() === "" ? null : label.trim()),
    onSuccess: () => {
      refresh();
      toast.success(`Name of ${server.name} saved.`);
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });

  function saveLabel(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    name.mutate();
  }

  return (
    <div className="grid gap-2 border-t border-border pt-3">
      <Field label="Mode">
        <Select
          aria-label={`Mode of ${server.name}`}
          compact
          value={server.automation_level}
          disabled={mode.isPending}
          options={MODE_OPTIONS}
          onChange={(event) => mode.mutate(event.target.value)}
        />
      </Field>
      <Field label="Tag">
        <Select
          aria-label={`Tag of ${server.name}`}
          compact
          value={server.tag ?? ""}
          disabled={tag.isPending}
          options={[
            { value: "", label: "No tag" },
            { value: "panel host", label: "Panel host (the server running this panel)" },
          ]}
          onChange={(event) => tag.mutate(event.target.value)}
        />
      </Field>
      <form className="flex flex-wrap items-end gap-2" onSubmit={saveLabel}>
        <Field label="Display name">
          <TextInput
            name={`label-${server.name}`}
            maxLength={64}
            placeholder={server.name}
            value={label}
            onChange={(event) => setLabel(event.target.value)}
          />
        </Field>
        <Button type="submit" size="sm" disabled={name.isPending}>
          Save name
        </Button>
      </form>
    </div>
  );
}
