import { CircleCheck, TriangleAlert } from "lucide-react";
import type { IncidentStory, StoryAction, StoryAdvice, StoryFound, StoryPoint } from "../../api/types";
import { storyVerdictTone } from "../../lib/tones";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { CommandLine } from "../../ui/CommandLine";
import { Disclosure } from "../../ui/Disclosure";
import { List, ListItem } from "../../ui/List";
import { Section } from "../../ui/Section";
import { Term } from "../../ui/Term";
import { EvidenceQuote } from "./EvidenceQuote";
import { agentLabel } from "./labels";

type StorySectionsProps = {
  story: IncidentStory;
  onClose?: () => void;
  leadWithAdvice?: boolean;
};

function Checked({ grounded }: { grounded: boolean }) {
  if (grounded) {
    return (
      <span className="inline-flex items-center gap-1 text-ok">
        <CircleCheck aria-hidden="true" size={14} />
        checked against the server
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-warning">
      <TriangleAlert aria-hidden="true" size={14} />
      not confirmed
    </span>
  );
}

function PointItem({ point }: { point: StoryPoint }) {
  return (
    <ListItem className="grid gap-1 border-l-2 border-border py-1 pl-4">
      <p className="m-0 break-words">{point.text}</p>
      <p className="m-0 flex flex-wrap gap-x-3 text-sm text-muted">
        <span>{agentLabel(point.agent)}</span>
        <Checked grounded={point.grounded} />
      </p>
      {point.evidence.length > 0 && (
        <Disclosure quiet summary="Where it was seen">
          <div className="grid gap-2">
            {point.evidence.map((item, index) => (
              <EvidenceQuote key={index} source={item.source} quote={item.quote} />
            ))}
          </div>
        </Disclosure>
      )}
    </ListItem>
  );
}

function FoundBody({ found }: { found: StoryFound }) {
  return (
    <>
      <p className="m-0 text-[17px]">{found.text}</p>
      {found.points.length > 0 && (
        <List gap="md">
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
    <ListItem className="grid gap-1 border-l-2 border-border py-1 pl-4">
      <div className="flex flex-wrap items-center gap-2">
        <strong className="font-semibold">{action.action_label}</strong>
        <Badge tone={storyVerdictTone(action.verdict)}>{action.verdict_label}</Badge>
      </div>
      {action.reasons.length > 0 && (
        <List variant="bullet" gap="xs" className="text-[15px] text-muted">
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

function AdviceSection({ advice, onClose, lead }: { advice: StoryAdvice; onClose?: () => void; lead: boolean }) {
  const body = (
    <>
      <p className="m-0 text-[17px]">{advice.text}</p>
      {advice.steps.length > 0 && (
        <List variant="numbered" gap="md" className="marker:font-semibold">
          {advice.steps.map((step, index) => (
            <ListItem key={index} className="pl-1">
              <div className="grid gap-2">
                <span>{step.text}</span>
                {step.command !== null && <CommandLine command={step.command} />}
              </div>
            </ListItem>
          ))}
        </List>
      )}
      {onClose !== undefined && (
        <Button variant="primary" onClick={onClose}>
          Close incident
        </Button>
      )}
    </>
  );
  return (
    <Section heading="What you should do">
      {lead ? <div className="grid gap-4 rounded-card border border-border border-l-4 border-l-accent bg-surface p-5">{body}</div> : body}
    </Section>
  );
}

export function StorySections({ story, onClose, leadWithAdvice = false }: StorySectionsProps) {
  const advice = <AdviceSection advice={story.what_you_should_do} onClose={onClose} lead={leadWithAdvice} />;
  return (
    <div className="grid">
      {leadWithAdvice && advice}
      <Section heading="What happened">
        <p className="m-0 text-[17px]">{story.what_happened.text}</p>
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
        <p className="m-0 text-[17px]">{story.what_we_did.text}</p>
        {story.what_we_did.considered.length > 0 && (
          <List gap="md">
            {story.what_we_did.considered.map((action, index) => (
              <ActionItem key={`${action.action}-${index}`} action={action} />
            ))}
          </List>
        )}
      </Section>
      {!leadWithAdvice && advice}
    </div>
  );
}
