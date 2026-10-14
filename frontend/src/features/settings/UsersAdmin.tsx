import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, CircleCheck, UserPlus } from "lucide-react";
import { useState } from "react";
import { disableUser, enableUser, getUsers, setUserRole } from "../../api/client";
import type { Role, UserView } from "../../api/types";
import { useSession } from "../../auth/session";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { DataTable, type Column } from "../../ui/DataTable";
import { Dialog } from "../../ui/Dialog";
import { ErrorState } from "../../ui/ErrorState";
import { RelativeTime } from "../../ui/RelativeTime";
import { Section } from "../../ui/Section";
import { Skeleton } from "../../ui/Skeleton";
import { useToast } from "../../ui/Toaster";
import {
  OWN_ACCOUNT_REASON,
  OWN_ROLE_REASON,
  ROLE_OPTIONS,
  accountStatusView,
  parseRole,
  roleLabel,
  settingsErrorText,
} from "./accountView";
import { CreateUserDialog } from "./CreateUserDialog";
import { INPUT_CLASS } from "./formStyles";
import { ResetPasswordDialog } from "./ResetPasswordDialog";

type PendingToggle = { user: UserView; disable: boolean };

type ToggleCopy = { title: string; description?: string; confirmLabel: string };

export function UsersAdmin() {
  const { me } = useSession();
  if (me.role !== "admin") {
    return null;
  }
  return <UsersSection ownUsername={me.username} />;
}

function UsersSection({ ownUsername }: { ownUsername: string }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const query = useQuery({ queryKey: ["users"], queryFn: () => getUsers() });
  const [creating, setCreating] = useState(false);
  const [resetting, setResetting] = useState<UserView | null>(null);
  const [toggling, setToggling] = useState<PendingToggle | null>(null);

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ["users"] });
  }

  const roleMutation = useMutation({
    mutationFn: ({ user, role }: { user: UserView; role: Role }) => setUserRole(user.id, role),
    onSuccess: (updated) => {
      refresh();
      toast.success(`Changed ${updated.username} to ${roleLabel(updated.role)}.`);
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ user, disable }: PendingToggle) => (disable ? disableUser(user.id) : enableUser(user.id)),
    onSuccess: (updated) => {
      refresh();
      setToggling(null);
      toast.success(
        updated.disabled ? `Disabled ${updated.username}. Their sessions ended.` : `Enabled ${updated.username}.`,
      );
    },
  });

  const busy = roleMutation.isPending || toggleMutation.isPending;

  function changeRole(user: UserView, value: string) {
    const role = parseRole(value);
    if (role !== null && role !== user.role) {
      roleMutation.mutate({ user, role });
    }
  }

  function openToggle(user: UserView) {
    toggleMutation.reset();
    setToggling({ user, disable: !user.disabled });
  }

  const columns: Column<UserView>[] = [
    {
      key: "username",
      header: "Username",
      cell: (user) => (
        <span className="font-medium break-all">
          {user.username}
          {user.username === ownUsername && <span className="ml-2 text-xs font-normal text-muted">(you)</span>}
        </span>
      ),
    },
    {
      key: "role",
      header: "Role",
      cell: (user) => {
        const own = user.username === ownUsername;
        return (
          <div className="grid gap-1">
            <select
              aria-label={`Role for ${user.username}`}
              value={user.role}
              disabled={own || busy}
              onChange={(event) => changeRole(user, event.target.value)}
              className={INPUT_CLASS}
            >
              {ROLE_OPTIONS.map((role) => (
                <option key={role} value={role}>
                  {roleLabel(role)}
                </option>
              ))}
            </select>
            {own && <span className="text-xs text-muted">{OWN_ROLE_REASON}</span>}
          </div>
        );
      },
    },
    {
      key: "status",
      header: "Status",
      cell: (user) => {
        const view = accountStatusView(user.disabled);
        return (
          <Badge tone={view.tone} icon={user.disabled ? Ban : CircleCheck}>
            {view.label}
          </Badge>
        );
      },
    },
    {
      key: "last-login",
      header: "Last login",
      cell: (user) =>
        user.last_login_at === null ? (
          <span className="text-muted">Never</span>
        ) : (
          <RelativeTime iso={user.last_login_at} />
        ),
    },
    {
      key: "actions",
      header: "Actions",
      cell: (user) => {
        const own = user.username === ownUsername;
        return (
          <div className="grid gap-1">
            <div className="flex flex-wrap gap-2">
              <Button size="sm" disabled={own || busy} onClick={() => setResetting(user)}>
                Reset password
              </Button>
              <Button size="sm" disabled={own || busy} onClick={() => openToggle(user)}>
                {user.disabled ? "Enable" : "Disable"}
              </Button>
            </div>
            {own && <span className="text-xs text-muted">{OWN_ACCOUNT_REASON}</span>}
          </div>
        );
      },
    },
  ];

  return (
    <Section heading="Users">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="m-0 text-sm text-muted">Only admins see this list. Every change is written to the activity log.</p>
        <Button size="sm" variant="primary" onClick={() => setCreating(true)}>
          <UserPlus aria-hidden="true" size={14} />
          Create user
        </Button>
      </div>
      {query.isPending && <Skeleton lines={4} />}
      {query.isError && (
        <ErrorState
          title="Could not load the users"
          message={settingsErrorText(query.error)}
          onRetry={() => void query.refetch()}
        />
      )}
      {query.isSuccess && (
        <>
          {roleMutation.isError && (
            <p role="alert" className="m-0 text-sm text-critical">
              {settingsErrorText(roleMutation.error)}
            </p>
          )}
          <DataTable label="Users" columns={columns} rows={query.data} rowKey={(user) => user.id} empty="No users yet." />
        </>
      )}
      <CreateUserDialog open={creating} onOpenChange={setCreating} />
      <ResetPasswordDialog user={resetting} onClose={() => setResetting(null)} />
      <ToggleUserDialog
        pending={toggling}
        busy={toggleMutation.isPending}
        error={toggleMutation.isError ? settingsErrorText(toggleMutation.error) : null}
        onConfirm={() => {
          if (toggling !== null) {
            toggleMutation.mutate(toggling);
          }
        }}
        onClose={() => setToggling(null)}
      />
    </Section>
  );
}

type ToggleUserDialogProps = {
  pending: PendingToggle | null;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
};

function ToggleUserDialog({ pending, busy, error, onConfirm, onClose }: ToggleUserDialogProps) {
  const copy = toggleCopy(pending);
  return (
    <Dialog
      open={pending !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
      title={copy.title}
      description={copy.description}
    >
      {pending !== null && (
        <div className="grid gap-4">
          {error !== null && (
            <p role="alert" className="m-0 text-sm text-critical">
              {error}
            </p>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button variant={pending.disable ? "danger" : "primary"} disabled={busy} onClick={onConfirm}>
              {copy.confirmLabel}
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}

function toggleCopy(pending: PendingToggle | null): ToggleCopy {
  if (pending === null) {
    return { title: "Change account", confirmLabel: "Confirm" };
  }
  const name = pending.user.username;
  return pending.disable
    ? {
        title: `Disable ${name}?`,
        description: "They cannot sign in, and their sessions end at once.",
        confirmLabel: "Disable account",
      }
    : {
        title: `Enable ${name}?`,
        description: "They can sign in again with their current password.",
        confirmLabel: "Enable account",
      };
}
