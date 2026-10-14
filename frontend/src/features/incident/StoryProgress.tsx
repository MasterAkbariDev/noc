import { Circle, CircleCheck, CircleDot, CircleX, Minus, type LucideIcon } from "lucide-react";
import type { StepState, StoryStep } from "../../api/types";
import type { Tone } from "../../lib/tones";
import { Badge } from "../../ui/Badge";
import { RelativeTime } from "../../ui/RelativeTime";
import { Section } from "../../ui/Section";

type StepView = { label: string; tone: Tone; icon: LucideIcon };

const STEP_VIEWS: Record<StepState, StepView> = {
  done: { label: "Done", tone: "ok", icon: CircleCheck },
  current: { label: "In progress", tone: "info", icon: CircleDot },
  pending: { label: "Not yet", tone: "neutral", icon: Circle },
  skipped: { label: "Skipped", tone: "neutral", icon: Minus },
  failed: { label: "Failed", tone: "critical", icon: CircleX },
};

function StepItem({ step }: { step: StoryStep }) {
  const view = STEP_VIEWS[step.state];
  return (
    <li
      aria-current={step.state === "current" ? "step" : undefined}
      className="flex items-start gap-3 md:flex-col md:items-center md:text-center"
    >
      <Badge tone={view.tone} icon={view.icon}>
        {view.label}
      </Badge>
      <span className="grid gap-0.5">
        <span className="font-medium">{step.label}</span>
        {step.at !== null ? (
          <RelativeTime iso={step.at} className="text-xs text-muted" />
        ) : (
          <span className="text-xs text-muted">No time yet</span>
        )}
      </span>
    </li>
  );
}

export function StoryProgress({ steps }: { steps: StoryStep[] }) {
  return (
    <Section heading="Progress">
      <ol className="m-0 grid list-none gap-4 p-0 md:grid-cols-6 md:gap-2">
        {steps.map((step) => (
          <StepItem key={step.key} step={step} />
        ))}
      </ol>
    </Section>
  );
}
