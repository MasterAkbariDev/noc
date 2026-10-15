import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, OctagonAlert, TriangleAlert } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { ApiError, decideOnAction } from "../../api/client";
import type { ActionView, ApprovalDecision } from "../../api/types";
import { absoluteTime } from "../../lib/format";
import {
  Badge,
  Button,
  Card,
  DescriptionList,
  Dialog,
  Field,
  Form,
  FormActions,
  FormMessage,
  List,
  ListItem,
  TextArea,
  TextInput,
  Term,
  useToast,
  type DescriptionItem,
} from "../../ui";
import { COMMENT_MAX_LENGTH, decisionErrorMessage, expiryText, isExpired, needsApprovalCode } from "./approval";
import { actionStatusLabel, plainLabel } from "./labels";

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
        <List gap="xs">
          {action.gate_failures.map((gate, index) => (
            <ListItem key={`${gate}-${index}`}>
              <span className="font-semibold text-critical">Failed: </span>
              <Term technical={gate}>{plainLabel(gate)}</Term>
            </ListItem>
          ))}
        </List>
      )}
      {action.reasons.length > 0 && (
        <List variant="bullet" gap="xs">
          {action.reasons.map((reason, index) => (
            <ListItem key={index}>{reason}</ListItem>
          ))}
        </List>
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
    <Form onSubmit={submit}>
      <p className="m-0 text-sm">
        {approving ? "Approve" : "Reject"} <strong className="font-semibold">{plainLabel(action.action_type)}</strong>{" "}
        on {action.resource_id}.
      </p>
      <p className="m-0 text-sm">Impact score: {pending.impactScore}</p>
      <HashLine hash={pending.actionHash} />
      <Field label="Comment (optional)">
        <TextArea value={comment} maxLength={COMMENT_MAX_LENGTH} rows={3} onChange={(event) => setComment(event.target.value)} />
      </Field>
      {codeStep && (
        <Field label="Authentication code">
          <TextInput
            name="approval-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            maxLength={16}
            value={code}
            onChange={(event) => setCode(event.target.value)}
          />
        </Field>
      )}
      {mutation.isError && <FormMessage>{decisionErrorMessage(mutation.error)}</FormMessage>}
      <Button type="submit" variant={approving ? "primary" : "danger"} disabled={mutation.isPending}>
        {mutation.isPending ? "Sending..." : approving ? "Approve action" : "Reject action"}
      </Button>
    </Form>
  );
}

function actionFacts(action: ActionView, now: number): DescriptionItem[] {
  const facts: DescriptionItem[] = [
    { key: "action", term: "Action", detail: <Term technical={action.action_type}>{plainLabel(action.action_type)}</Term> },
    { key: "target", term: "Target", detail: <span className="break-all">{action.resource_id}</span> },
    {
      key: "permission",
      term: "Permission",
      detail: <Term technical={action.permission_class}>{plainLabel(action.permission_class)}</Term>,
    },
    { key: "impact", term: "Impact score", detail: action.impact_score },
  ];
  if (action.approval_expires_at !== null) {
    facts.push({
      key: "expiry",
      term: "Expiry",
      detail: (
        <time dateTime={action.approval_expires_at} title={absoluteTime(action.approval_expires_at)}>
          {expiryText(action.approval_expires_at, now)}
        </time>
      ),
    });
  }
  return facts;
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
    <Card title="Waiting for your approval" icon={TriangleAlert} iconTone="warning" className="grid gap-4 border-warning/60">
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
      <DescriptionList items={actionFacts(action, now)} />
      {expired && (
        <p role="status" className="m-0 text-sm font-semibold">
          This request has expired. It can no longer be approved or rejected.
        </p>
      )}
      <GateChecks action={action} />
      <HashLine hash={action.action_hash} />
      {canDecide ? (
        <FormActions>
          <Button variant="primary" disabled={expired} onClick={() => setPending(pendingFor("approved", action))}>
            Approve
          </Button>
          <Button variant="danger" disabled={expired} onClick={() => setPending(pendingFor("rejected", action))}>
            Reject
          </Button>
        </FormActions>
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
