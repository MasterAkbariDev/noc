export function EvidenceQuote({ source, quote }: { source: string; quote: string }) {
  return (
    <figure className="m-0 grid gap-1">
      <figcaption className="text-xs text-muted">Seen in: {source}</figcaption>
      {quote !== "" && (
        <blockquote
          dir="ltr"
          className="m-0 break-all rounded-control border-l-2 border-border bg-surface-2 px-3 py-1.5 font-mono text-xs"
        >
          {quote}
        </blockquote>
      )}
    </figure>
  );
}
