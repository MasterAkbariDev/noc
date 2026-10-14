import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { closeIncident } from "../api/client";
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

export function CloseIncidentForm({ incidentId, status }: { incidentId: string; status: string }) {
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
    <section className="card">
      <h2>Close this incident</h2>
      <p className="muted">The agents escalated this incident. Record what was done before closing it.</p>
      <form onSubmit={submit}>
        <label>
          Resolution note (required)
          <textarea
            value={note}
            maxLength={RESOLUTION_NOTE_MAX_LENGTH}
            rows={4}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
        <label>
          Corrected root cause (optional)
          <select value={rootCause} onChange={(event) => setRootCause(event.target.value)}>
            <option value="">No change</option>
            {ROOT_CAUSE_CODES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input type="checkbox" checked={checked} onChange={(event) => setChecked(event.target.checked)} />
          I checked this incident
        </label>
        {mutation.isError && <p role="alert" className="error">{errorMessage(mutation.error)}</p>}
        <button type="submit" disabled={!canSubmit}>
          {mutation.isPending ? "Closing..." : "Close incident"}
        </button>
      </form>
    </section>
  );
}
