import { Link } from "react-router";
import type { IncidentStory } from "../../api/types";
import { IncidentStatusBadge } from "../../ui/IncidentStatusBadge";
import { PageHeader } from "../../ui/PageHeader";
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
    <Link to={`/servers/${encodeURIComponent(serverId)}`} className="text-accent underline">
      {target}
    </Link>
  );
}

export function StoryHeader({ story, openedAt, serverId }: StoryHeaderProps) {
  return (
    <div className="grid gap-3">
      <PageHeader
        title={story.title}
        status={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <SeverityBadge severity={story.severity} />
            <IncidentStatusBadge status={story.status} />
            <TargetName target={story.target} serverId={serverId} />
            {openedAt !== null && (
              <span>
                Opened <RelativeTime iso={openedAt} />
              </span>
            )}
          </span>
        }
      />
      <p className="m-0 text-base">{story.headline}</p>
    </div>
  );
}
