import { CircleCheck, TriangleAlert } from "lucide-react";
import type { IncidentStory, StoryAction, StoryFound, StoryPoint } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { CommandLine } from "../../ui/CommandLine";
import { List, ListItem } from "../../ui/List";
import { Section } from "../../ui/Section";
import { Term } from "../../ui/Term";
import { storyVerdictTone } from "../../lib/tones";
import { EvidenceQuote } from "./EvidenceQuote";
import { agentLabel } from "./labels";

type StorySectionsProps = {
  story: IncidentStory;
  onClose?: () => void;
};

function PointItem({ point }: { point: StoryPoint }) {
  return (
    <ListItem className="grid gap-1 rounded-control border border-border p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">{agentLabel(point.agent)}</span>
        {point.grounded ? (
          <Badge tone="ok" icon={CircleCheck}>
            checked against the server
          </Badge>
        ) : (
          <Badge tone="warning" icon={TriangleAlert}>
            not confirmed
          </Badge>
        )}
      </div>
      <p className="m-0">{point.text}</p>
      {point.evidence.map((item, index) => (
        <EvidenceQuote key={index} source={item.source} quote={item.quote} />
      ))}
    </ListItem>
  );
}

function FoundBody({ found }: { found: StoryFound }) {
  return (
    <>
      <p className="m-0">{found.text}</p>
      {found.points.length > 0 && (
        <List gap="sm">
          {found.points.map((point, index) => (
            <PointItem key={`${point.label}-${index}`} point={point} />
          ))}
        </List>
      )}
    </>
  );
}

function ActionItem({ action }: { action: StoryAction }) {
  return (
    <ListItem className="grid gap-1 rounded-control border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <strong className="font-semibold">{action.action_label}</strong>
        <Badge tone={storyVerdictTone(action.verdict)}>{action.verdict_label}</Badge>
      </div>
      {action.reasons.length > 0 && (
        <List variant="bullet" gap="xs" className="text-sm">
          {action.reasons.map((reason, index) => (
            <ListItem key={index}>{reason}</ListItem>
          ))}
        </List>
      )}
      {action.technical.length > 0 && (
        <p className="m-0 text-sm text-muted">
          <Term technical={action.technical.join(", ")}>Policy details</Term>
        </p>
      )}
    </ListItem>
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
          <List gap="sm">
            {story.what_we_did.considered.map((action, index) => (
              <ActionItem key={`${action.action}-${index}`} action={action} />
            ))}
          </List>
        )}
      </Section>
      <Section heading="What you should do">
        <p className="m-0">{advice.text}</p>
        {advice.steps.length > 0 && (
          <List variant="numbered" gap="xs">
            {advice.steps.map((step, index) => (
              <ListItem key={index}>
                {step.text}
                {step.command !== null && <CommandLine command={step.command} />}
              </ListItem>
            ))}
          </List>
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
