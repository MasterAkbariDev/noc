import { useDocumentTitle } from "../shell/useDocumentTitle";
import { PageHeader } from "../ui/PageHeader";

export function SystemPage() {
  useDocumentTitle("System");
  return <PageHeader title="System" />;
}
