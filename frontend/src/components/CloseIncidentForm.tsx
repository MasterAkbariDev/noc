import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { closeIncident } from "../api/client";
import { Button } from "../ui/Button";
import { errorMessage } from "./format";

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

  const fieldClass = "w-full rounded-control border border-border bg-surface px-3 py-2 text-sm font-normal text-fg";

  return (
    <form onSubmit={submit} className="grid gap-4">
      <p className="m-0 text-sm text-muted">The agents escalated this incident. Record what was done before closing it.</p>
      <label className="grid gap-1 text-sm font-medium">
        Resolution note (required)
        <textarea
          className={fieldClass}
          value={note}
          maxLength={RESOLUTION_NOTE_MAX_LENGTH}
          rows={4}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      <label className="grid gap-1 text-sm font-medium">
        Corrected root cause (optional)
        <select className={fieldClass} value={rootCause} onChange={(event) => setRootCause(event.target.value)}>
          <option value="">No change</option>
          {ROOT_CAUSE_CODES.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="size-4 accent-accent"
          checked={checked}
          onChange={(event) => setChecked(event.target.checked)}
        />
        I checked this incident
      </label>
      {mutation.isError && (
        <p role="alert" className="m-0 text-sm text-critical">
          {errorMessage(mutation.error)}
        </p>
      )}
      <Button type="submit" variant="primary" disabled={!canSubmit}>
        {mutation.isPending ? "Closing..." : "Close incident"}
      </Button>
    </form>
  );
}
