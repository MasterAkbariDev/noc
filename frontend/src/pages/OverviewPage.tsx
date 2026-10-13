import { useDocumentTitle } from "../shell/useDocumentTitle";
import { PageHeader } from "../ui/PageHeader";

export function OverviewPage() {
  useDocumentTitle("Overview");
  return <PageHeader title="Overview" />;
}
