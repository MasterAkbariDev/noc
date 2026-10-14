import { useState } from "react";
import { Button } from "../../ui/Button";

type CopyState = "idle" | "copied" | "failed";

const COPY_MESSAGES: Record<CopyState, string> = {
  idle: "",
  copied: "Report copied.",
  failed: "Copy did not work. Select the text and copy it by hand.",
};

export function ReportTab({ report }: { report: string | null }) {
  const [copyState, setCopyState] = useState<CopyState>("idle");

  if (report === null) {
    return <p className="m-0 text-muted">Report not ready yet.</p>;
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={() => void copy(report)}>
          Copy report
        </Button>
        <span role="status" className="text-sm text-muted">
          {COPY_MESSAGES[copyState]}
        </span>
      </div>
      <pre className="m-0 max-h-[70vh] overflow-auto rounded-card border border-border bg-surface-2 p-4 text-sm break-words whitespace-pre-wrap">
        {report}
      </pre>
    </div>
  );
}
