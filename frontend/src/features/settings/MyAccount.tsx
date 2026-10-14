import { useSession } from "../../auth/session";
import { Card } from "../../ui/Card";
import { ChangePasswordForm } from "./ChangePasswordForm";
import { TwoFactorCard } from "./TwoFactorCard";
import { roleLabel } from "./accountView";

export function MyAccount() {
  const { me } = useSession();

  return (
    <Card>
      <dl className="m-0 grid gap-3 text-sm sm:grid-cols-[max-content_minmax(0,1fr)] sm:gap-x-6">
        <dt className="text-muted">Username</dt>
        <dd className="m-0 font-medium break-all">{me.username}</dd>
        <dt className="text-muted">Role</dt>
        <dd className="m-0 font-medium">{roleLabel(me.role)}</dd>
      </dl>
      <div className="mt-6 border-t border-border pt-6">
        <ChangePasswordForm />
      </div>
      <div className="mt-6 border-t border-border pt-6">
        <TwoFactorCard />
      </div>
    </Card>
  );
}
