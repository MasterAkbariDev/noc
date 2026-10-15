import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { closeIncident } from "../api/client";
import { Button, Checkbox, Field, Form, FormMessage, Select, TextArea, useToast } from "../ui";
import { errorMessage } from "../lib/format";
import { plainLabel } from "../features/incident/labels";

export const RESOLUTION_NOTE_MAX_LENGTH = 2000;

export const ROOT_CAUSE_CODES = [
  "cpu_runaway_process",
  "memory_leak",
  "oom_kill_loop",
  "disk_full_logs",
  "disk_full_data",
  "inode_exhaustion",
  "service_crashed",
  "service_misconfigured",
  "bad_deploy",
  "dependency_db_unavailable",
  "db_connection_exhaustion",
  "upstream_latency",
  "network_latency",
  "network_partition",
  "dns_resolution_failure",
  "tls_certificate_invalid",
  "clock_skew",
  "noisy_neighbor",
  "brute_force_ssh",
  "suspicious_process",
  "transient_spike",
  "unknown",
] as const;

type CloseIncidentFormProps = {
  incidentId: string;
  status: string;
  onClosed?: () => void;
};

export function CloseIncidentForm({ incidentId, status, onClosed }: CloseIncidentFormProps) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [note, setNote] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [checked, setChecked] = useState(false);

  const mutation = useMutation({
    mutationFn: () =>
      closeIncident(incidentId, {
        resolution_note: note.trim(),
        corrected_root_cause_code: rootCause === "" ? null : rootCause,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["incidents"] });
      void queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
      void queryClient.invalidateQueries({ queryKey: ["story", incidentId] });
      void queryClient.invalidateQueries({ queryKey: ["overview"] });
      toast.success("Incident closed.");
      onClosed?.();
    },
  });

  if (status !== "ESCALATED") {
    return null;
  }

  const canSubmit = note.trim() !== "" && checked && !mutation.isPending;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (canSubmit) {
      mutation.mutate();
    }
  }

  return (
    <Form onSubmit={submit}>
      <p className="m-0 text-sm text-muted">The agents escalated this incident. Record what was done before closing it.</p>
      <Field label="Resolution note (required)">
        <TextArea value={note} maxLength={RESOLUTION_NOTE_MAX_LENGTH} rows={4} onChange={(event) => setNote(event.target.value)} />
      </Field>
      <Field label="Corrected root cause (optional)">
        <Select
          value={rootCause}
          options={[
            { value: "", label: "No change" },
            ...ROOT_CAUSE_CODES.map((code) => ({ value: code, label: plainLabel(code) })),
          ]}
          onChange={(event) => setRootCause(event.target.value)}
        />
      </Field>
      <Checkbox label="I checked this incident" checked={checked} onChange={(event) => setChecked(event.target.checked)} />
      {mutation.isError && <FormMessage>{errorMessage(mutation.error)}</FormMessage>}
      <Button type="submit" variant="primary" disabled={!canSubmit}>
        {mutation.isPending ? "Closing..." : "Close incident"}
      </Button>
    </Form>
  );
}
