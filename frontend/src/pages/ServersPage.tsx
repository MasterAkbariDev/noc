import { useDocumentTitle } from "../shell/useDocumentTitle";
import { PageHeader } from "../ui/PageHeader";

export function ServersPage() {
  useDocumentTitle("Servers");
  return <PageHeader title="Servers" />;
}
