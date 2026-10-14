import { MyAccount } from "../features/settings/MyAccount";
import { UsersAdmin } from "../features/settings/UsersAdmin";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { PageHeader } from "../ui/PageHeader";
import { Section } from "../ui/Section";

export function SettingsPage() {
  useDocumentTitle("Settings");
  return (
    <>
      <PageHeader title="Settings" status="Your account, and for admins, the people who can sign in to this panel." />
      <Section heading="My account">
        <MyAccount />
      </Section>
      <UsersAdmin />
    </>
  );
}
