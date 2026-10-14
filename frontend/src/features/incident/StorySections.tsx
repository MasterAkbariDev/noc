import { CircleCheck, TriangleAlert } from "lucide-react";
import type { IncidentStory, StoryAction, StoryFound, StoryPoint } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Section } from "../../ui/Section";
import { Term } from "../../ui/Term";
import { verdictTone } from "./labels";

type StorySectionsProps = {
  story: IncidentStory;
  onClose?: () => void;
};

function PointItem({ point }: { point: StoryPoint }) {
  return (
    <li className="grid gap-1 rounded-control border border-border p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">{point.agent}</span>
        <span className="font-medium">{point.label}</span>
        {point.grounded ? (
          <Badge tone="ok" icon={CircleCheck}>
            backed by evidence
          </Badge>
        ) : (
          <Badge tone="warning" icon={TriangleAlert}>
            not backed by evidence
          </Badge>
        )}
      </div>
      <p className="m-0">{point.text}</p>
      {point.refs.length > 0 && <p className="m-0 text-xs text-muted">Evidence: {point.refs.join(", ")}</p>}
    </li>
  );
}

function FoundBody({ found }: { found: StoryFound }) {
  return (
    <>
      <p className="m-0">{found.text}</p>
      {found.points.length > 0 && (
        <ul className="m-0 grid list-none gap-2 p-0">
          {found.points.map((point, index) => (
            <PointItem key={`${point.label}-${index}`} point={point} />
          ))}
        </ul>
      )}
    </>
  );
}

function ActionItem({ action }: { action: StoryAction }) {
  return (
    <li className="grid gap-1 rounded-control border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <strong className="font-semibold">{action.action_label}</strong>
        <Badge tone={verdictTone(action.verdict)}>{action.verdict_label}</Badge>
      </div>
      {action.reasons.length > 0 && (
        <ul className="m-0 list-disc pl-5 text-sm">
          {action.reasons.map((reason, index) => (
            <li key={index}>{reason}</li>
          ))}
        </ul>
      )}
      {action.technical.length > 0 && (
        <p className="m-0 text-sm text-muted">
          <Term technical={action.technical.join(", ")}>Policy details</Term>
        </p>
      )}
    </li>
  );
}

export function StorySections({ story, onClose }: StorySectionsProps) {
  const advice = story.what_you_should_do;
  return (
    <div className="grid gap-8">
      <Section heading="What happened">
        <p className="m-0">{story.what_happened.text}</p>
        {story.what_happened.technical !== null && (
          <p className="m-0 text-sm text-muted">
            <Term technical={story.what_happened.technical}>Alert details</Term>
          </p>
        )}
      </Section>
      <Section heading="What we found">
        <FoundBody found={story.what_we_found} />
      </Section>
      <Section heading="What we did">
        <p className="m-0">{story.what_we_did.text}</p>
        {story.what_we_did.considered.length > 0 && (
          <ul className="m-0 grid list-none gap-2 p-0">
            {story.what_we_did.considered.map((action, index) => (
              <ActionItem key={`${action.action}-${index}`} action={action} />
            ))}
          </ul>
        )}
      </Section>
      <Section heading="What you should do">
        <p className="m-0">{advice.text}</p>
        {advice.steps.length > 0 && (
          <ol className="m-0 grid list-decimal gap-1 pl-5">
            {advice.steps.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
        )}
        {onClose !== undefined && (
          <Button variant="primary" onClick={onClose}>
            Close incident
          </Button>
        )}
      </Section>
    </div>
  );
}
