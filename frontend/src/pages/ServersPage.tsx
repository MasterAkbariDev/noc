import { ServersList } from "../features/servers/ServersList";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { PageHeader } from "../ui/PageHeader";

export function ServersPage() {
  useDocumentTitle("Servers");
  return (
    <>
      <PageHeader eyebrow="Monitor" title="Servers" status="Every machine the NOC watches, with its health and automation level." />
      <ServersList />
    </>
  );
}
