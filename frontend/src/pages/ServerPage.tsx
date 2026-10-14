import { useParams } from "react-router";
import { ServerBody } from "../features/servers/ServerBody";
import { useServerQuery } from "../features/servers/queries";
import { ServerStatusLine } from "../features/servers/ServerParts";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { PageHeader } from "../ui/PageHeader";

export function ServerPage() {
  const { id = "" } = useParams();
  const query = useServerQuery(id);
  const name = query.data?.name ?? "Server";
  useDocumentTitle(name);
  return (
    <>
      <PageHeader
        title={name}
        status={query.data === undefined ? undefined : <ServerStatusLine server={query.data} />}
      />
      <ServerBody query={query} />
    </>
  );
}
