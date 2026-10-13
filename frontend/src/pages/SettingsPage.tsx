import { useDocumentTitle } from "../shell/useDocumentTitle";
import { PageHeader } from "../ui/PageHeader";

export function SettingsPage() {
  useDocumentTitle("Settings");
  return <PageHeader title="Settings" />;
}
