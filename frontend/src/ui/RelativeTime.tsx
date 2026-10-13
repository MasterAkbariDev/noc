import { absoluteTime, relativeTime } from "../lib/format";

type RelativeTimeProps = {
  iso: string;
  className?: string;
};

export function RelativeTime({ iso, className }: RelativeTimeProps) {
  return (
    <time dateTime={iso} title={absoluteTime(iso)} className={className}>
      {relativeTime(iso)}
    </time>
  );
}
