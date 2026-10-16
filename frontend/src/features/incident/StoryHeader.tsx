import { Link } from "react-router";
import type { IncidentStory } from "../../api/types";
import { withoutTitle } from "../../lib/format";
import { IncidentStatusBadge } from "../../ui/IncidentStatusBadge";
import { RelativeTime } from "../../ui/RelativeTime";
import { SeverityBadge } from "../../ui/SeverityBadge";

type StoryHeaderProps = {
  story: IncidentStory;
  openedAt: string | null;
  serverId: string | null;
};

function TargetName({ target, serverId }: { target: string; serverId: string | null }) {
  if (serverId === null) {
    return <span>{target}</span>;
  }
  return (
    <Link to={`/servers/${encodeURIComponent(serverId)}`} className="text-accent underline underline-offset-4">
      {target}
    </Link>
  );
}

export function StoryHeader({ story, openedAt, serverId }: StoryHeaderProps) {
  return (
    <header className="grid max-w-3xl gap-3">
      <h1 className="m-0 text-[clamp(1.6rem,3.4vw,2.25rem)] leading-tight font-semibold tracking-tight break-words">{story.title}</h1>
      <p className="m-0 text-lg text-muted break-words">{withoutTitle(story.title, story.headline)}</p>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted">
        <SeverityBadge severity={story.severity} />
        <IncidentStatusBadge status={story.status} />
        <span>
          On <TargetName target={story.target} serverId={serverId} />
        </span>
        {openedAt !== null && (
          <span>
            Opened <RelativeTime iso={openedAt} />
          </span>
        )}
      </div>
    </header>
  );
}
