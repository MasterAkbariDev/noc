import { useDocumentTitle } from "../shell/useDocumentTitle";
import { PageHeader } from "../ui/PageHeader";

export function ServerPage() {
  useDocumentTitle("Server");
  return <PageHeader title="Server" />;
}
