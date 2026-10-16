import { Check, Minus, X, type LucideIcon } from "lucide-react";
import type { StepState, StoryStep } from "../../api/types";
import { cx } from "../../lib/cx";
import { List, ListItem } from "../../ui/List";
import { RelativeTime } from "../../ui/RelativeTime";
import { Section } from "../../ui/Section";

type StepView = { label: string; icon: LucideIcon | null; mark: string };

const STEP_VIEWS: Record<StepState, StepView> = {
  done: { label: "Done", icon: Check, mark: "border-ok bg-ok text-surface" },
  current: { label: "In progress", icon: null, mark: "step-current border-accent bg-surface" },
  pending: { label: "Not yet", icon: null, mark: "border-border-strong bg-surface" },
  skipped: { label: "Skipped", icon: Minus, mark: "border-border-strong bg-surface-2 text-muted" },
  failed: { label: "Failed", icon: X, mark: "border-critical bg-critical text-surface" },
};

function StepItem({ step }: { step: StoryStep }) {
  const view = STEP_VIEWS[step.state];
  const Icon = view.icon;
  const quiet = step.state === "pending" || step.state === "skipped";
  return (
    <ListItem
      aria-current={step.state === "current" ? "step" : undefined}
      className="relative flex gap-3 pb-5 last:pb-0 before:absolute before:top-6 before:bottom-0 before:left-[11px] before:w-0.5 before:bg-border before:content-[''] last:before:hidden"
    >
      <span aria-hidden="true" className={cx("relative z-10 inline-grid size-6 shrink-0 place-items-center rounded-full border-2", view.mark)}>
        {Icon !== null ? <Icon size={13} strokeWidth={3} /> : step.state === "current" && <span className="size-2 rounded-full bg-accent" />}
      </span>
      <span className="grid gap-0.5">
        <span className={cx("leading-6 font-semibold", quiet && "font-normal text-muted")}>{step.label}</span>
        <span className="text-sm text-muted">
          <span>{view.label}</span>
          {step.at !== null && (
            <>
              {", "}
              <RelativeTime iso={step.at} />
            </>
          )}
        </span>
      </span>
    </ListItem>
  );
}

export function StoryProgress({ steps }: { steps: StoryStep[] }) {
  return (
    <Section heading="Progress">
      <List ordered gap="xs" className="gap-0">
        {steps.map((step) => (
          <StepItem key={step.key} step={step} />
        ))}
      </List>
    </Section>
  );
}
