import { useDocumentTitle } from "../shell/useDocumentTitle";
import { PageHeader } from "../ui/PageHeader";

export function ActivityPage() {
  useDocumentTitle("Activity");
  return <PageHeader title="Activity" />;
}
