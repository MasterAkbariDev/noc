import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, OctagonAlert, TriangleAlert } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { ApiError, decideOnAction } from "../../api/client";
import type { ActionView, ApprovalDecision } from "../../api/types";
import { absoluteTime } from "../../lib/format";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Card } from "../../ui/Card";
import { Dialog } from "../../ui/Dialog";
import { Term } from "../../ui/Term";
import { useToast } from "../../ui/Toaster";
import { COMMENT_MAX_LENGTH, decisionErrorMessage, expiryText, isExpired, needsApprovalCode } from "./approval";
import { actionStatusLabel, plainLabel } from "./labels";

const FIELD_CLASS = "w-full rounded-control border border-border bg-surface px-3 py-2 text-sm font-normal text-fg";
const EXPIRY_TICK_MS = 30_000;

type ApprovalCardProps = {
  incidentId: string;
  action: ActionView;
  canDecide: boolean;
};

type PendingDecision = {
  decision: ApprovalDecision;
  actionHash: string;
  impactScore: number;
};

type CopyState = "idle" | "copied" | "failed";

function pendingFor(decision: ApprovalDecision, action: ActionView): PendingDecision {
  return { decision, actionHash: action.action_hash, impactScore: action.impact_score };
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function HashLine({ hash }: { hash: string }) {
  const [copyState, setCopyState] = useState<CopyState>("idle");

  async function copy() {
    setCopyState((await copyText(hash)) ? "copied" : "failed");
  }

  const buttonText = copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy";

  return (
    <div className="grid gap-1 text-sm">
      <span className="text-muted">The approval is tied to this exact action hash:</span>
      <div className="flex flex-wrap items-center gap-2">
        <code className="min-w-0 rounded-control bg-surface-2 px-2 py-1 font-mono text-xs break-all">{hash}</code>
        <Button variant="secondary" size="sm" onClick={() => void copy()}>
          {copyState === "copied" ? <Check aria-hidden="true" size={14} /> : <Copy aria-hidden="true" size={14} />}
          {buttonText}
        </Button>
      </div>
    </div>
  );
}

function GateChecks({ action }: { action: ActionView }) {
  return (
    <div className="grid gap-2 text-sm">
      <h3 className="m-0 text-sm font-semibold">Gate checks</h3>
      {action.gate_failures.length === 0 ? (
        <p className="m-0 text-muted">No gate check failed.</p>
      ) : (
        <ul className="m-0 grid list-none gap-1 p-0">
          {action.gate_failures.map((gate, index) => (
            <li key={`${gate}-${index}`}>
              <span className="font-semibold text-critical">Failed: </span>
              <Term technical={gate}>{plainLabel(gate)}</Term>
            </li>
          ))}
        </ul>
      )}
      {action.reasons.length > 0 && (
        <ul className="m-0 list-disc pl-5">
          {action.reasons.map((reason, index) => (
            <li key={index}>{reason}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DecisionForm({
  incidentId,
  action,
  pending,
  onDone,
}: {
  incidentId: string;
  action: ActionView;
  pending: PendingDecision;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [comment, setComment] = useState("");
  const [code, setCode] = useState("");
  const [codeStep, setCodeStep] = useState(false);
  const trimmedComment = comment.trim();
  const approving = pending.decision === "approved";

  const mutation = useMutation({
    mutationFn: () =>
      decideOnAction(incidentId, action.id, {
        decision: pending.decision,
        action_hash: pending.actionHash,
        comment: trimmedComment === "" ? null : trimmedComment,
        ...(codeStep && code.trim() !== "" ? { totp: code.trim() } : {}),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
      void queryClient.invalidateQueries({ queryKey: ["story", incidentId] });
      void queryClient.invalidateQueries({ queryKey: ["incidents"] });
      void queryClient.invalidateQueries({ queryKey: ["overview"] });
      toast.success(approving ? "Action approved." : "Action rejected.");
      onDone();
    },
    onError: (error) => {
      if (needsApprovalCode(error)) {
        setCodeStep(true);
        setCode("");
      }
      if (error instanceof ApiError && error.status === 409) {
        void queryClient.refetchQueries({ queryKey: ["incident", incidentId] });
      }
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!mutation.isPending) {
      mutation.mutate();
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <p className="m-0 text-sm">
        {approving ? "Approve" : "Reject"} <strong className="font-semibold">{plainLabel(action.action_type)}</strong>{" "}
        on {action.resource_id}.
      </p>
      <p className="m-0 text-sm">Impact score: {pending.impactScore}</p>
      <HashLine hash={pending.actionHash} />
      <label className="grid gap-1 text-sm font-medium">
        Comment (optional)
        <textarea
          className={FIELD_CLASS}
          value={comment}
          maxLength={COMMENT_MAX_LENGTH}
          rows={3}
          onChange={(event) => setComment(event.target.value)}
        />
      </label>
      {codeStep && (
        <label className="grid gap-1 text-sm font-medium">
          Authentication code
          <input
            className={FIELD_CLASS}
            name="approval-code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            maxLength={16}
            value={code}
            onChange={(event) => setCode(event.target.value)}
          />
        </label>
      )}
      {mutation.isError && (
        <p role="alert" className="m-0 text-sm text-critical">
          {decisionErrorMessage(mutation.error)}
        </p>
      )}
      <Button type="submit" variant={approving ? "primary" : "danger"} disabled={mutation.isPending}>
        {mutation.isPending ? "Sending..." : approving ? "Approve action" : "Reject action"}
      </Button>
    </form>
  );
}

export function ApprovalCard({ incidentId, action, canDecide }: ApprovalCardProps) {
  const [pending, setPending] = useState<PendingDecision | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const expired = isExpired(action.approval_expires_at, now);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), EXPIRY_TICK_MS);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <Card title="Waiting for your approval" className="grid gap-4 border-warning">
      <p className="m-0 text-sm">
        {canDecide ? "This incident is waiting for your decision." : "Waiting for an operator's decision."}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="warning" icon={TriangleAlert}>
          {actionStatusLabel(action.status)}
        </Badge>
        {action.high_impact && (
          <Badge tone="critical" icon={OctagonAlert}>
            High impact
          </Badge>
        )}
      </div>
      <dl className="m-0 grid gap-2 text-sm sm:grid-cols-[max-content_minmax(0,1fr)]">
        <dt className="text-muted">Action</dt>
        <dd className="m-0">
          <Term technical={action.action_type}>{plainLabel(action.action_type)}</Term>
        </dd>
        <dt className="text-muted">Target</dt>
        <dd className="m-0 break-all">{action.resource_id}</dd>
        <dt className="text-muted">Permission</dt>
        <dd className="m-0">
          <Term technical={action.permission_class}>{plainLabel(action.permission_class)}</Term>
        </dd>
        <dt className="text-muted">Impact score</dt>
        <dd className="m-0">{action.impact_score}</dd>
        {action.approval_expires_at !== null && (
          <>
            <dt className="text-muted">Expiry</dt>
            <dd className="m-0">
              <time dateTime={action.approval_expires_at} title={absoluteTime(action.approval_expires_at)}>
                {expiryText(action.approval_expires_at, now)}
              </time>
            </dd>
          </>
        )}
      </dl>
      {expired && (
        <p role="status" className="m-0 text-sm font-semibold">
          This request has expired. It can no longer be approved or rejected.
        </p>
      )}
      <GateChecks action={action} />
      <HashLine hash={action.action_hash} />
      {canDecide ? (
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" disabled={expired} onClick={() => setPending(pendingFor("approved", action))}>
            Approve
          </Button>
          <Button variant="danger" disabled={expired} onClick={() => setPending(pendingFor("rejected", action))}>
            Reject
          </Button>
        </div>
      ) : (
        <p className="m-0 text-sm text-muted">Only an operator or an admin can approve or reject this action.</p>
      )}
      <Dialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) {
            setPending(null);
          }
        }}
        title={pending?.decision === "rejected" ? "Reject this action" : "Approve this action"}
      >
        {pending !== null && (
          <DecisionForm
            incidentId={incidentId}
            action={action}
            pending={pending}
            onDone={() => setPending(null)}
          />
        )}
      </Dialog>
    </Card>
  );
}
