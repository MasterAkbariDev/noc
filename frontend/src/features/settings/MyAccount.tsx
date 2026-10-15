import { useSession } from "../../auth/session";
import { Card } from "../../ui/Card";
import { DescriptionList } from "../../ui/List";
import { ChangePasswordForm } from "./ChangePasswordForm";
import { TwoFactorCard } from "./TwoFactorCard";
import { roleLabel } from "./accountView";

export function MyAccount() {
  const { me } = useSession();

  return (
    <Card>
      <DescriptionList
        items={[
          { key: "username", term: "Username", detail: <span className="font-medium break-all">{me.username}</span> },
          { key: "role", term: "Role", detail: <span className="font-medium">{roleLabel(me.role)}</span> },
        ]}
      />
      <div className="mt-6 border-t border-border pt-6">
        <ChangePasswordForm />
      </div>
      <div className="mt-6 border-t border-border pt-6">
        <TwoFactorCard />
      </div>
    </Card>
  );
}
