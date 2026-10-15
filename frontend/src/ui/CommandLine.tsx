import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { IconButton } from "./IconButton";

const COPIED_MS = 1500;

export function CommandLine({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), COPIED_MS);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div dir="ltr" className="mt-1 flex max-w-full items-start gap-1 rounded-control border border-border bg-surface-2 py-1 pl-3 pr-1">
      <code className="w-0 min-w-0 flex-1 overflow-x-auto whitespace-pre py-1 font-mono text-xs text-fg">{command}</code>
      <IconButton label={copied ? "Copied" : "Copy command"} icon={copied ? Check : Copy} onClick={() => void copy()} />
    </div>
  );
}
