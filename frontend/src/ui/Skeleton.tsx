export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div role="status" className="grid gap-2">
      <span className="sr-only">Loading…</span>
      {Array.from({ length: lines }, (_, index) => (
        <span
          key={index}
          aria-hidden="true"
          className="block h-4 animate-pulse rounded-control bg-surface-2 motion-reduce:animate-none"
          style={{ width: `${100 - index * 12}%` }}
        />
      ))}
    </div>
  );
}
