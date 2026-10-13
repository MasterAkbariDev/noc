import { Link } from "react-router";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { PageHeader } from "../ui/PageHeader";

export function NotFoundPage() {
  useDocumentTitle("Page not found");
  return (
    <>
      <PageHeader title="Page not found" />
      <p className="m-0 text-muted">
        <Link to="/" className="text-accent underline underline-offset-4">
          Back to overview
        </Link>
      </p>
    </>
  );
}
