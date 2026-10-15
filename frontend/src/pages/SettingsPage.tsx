import { LlmAdmin } from "../features/llm/LlmAdmin";
import { TelegramAdmin } from "../features/notify/TelegramAdmin";
import { MyAccount } from "../features/settings/MyAccount";
import { UsersAdmin } from "../features/settings/UsersAdmin";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { PageHeader } from "../ui/PageHeader";
import { Section } from "../ui/Section";

export function SettingsPage() {
  useDocumentTitle("Settings");
  return (
    <>
      <PageHeader eyebrow="Administration" title="Settings" status="Your account, and for admins, the people who can sign in, the model providers the agents use and Telegram notifications." />
      <Section heading="My account">
        <MyAccount />
      </Section>
      <UsersAdmin />
      <LlmAdmin />
      <TelegramAdmin />
    </>
  );
}
