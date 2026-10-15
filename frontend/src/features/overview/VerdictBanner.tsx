import { Activity, CircleCheck, OctagonAlert, TriangleAlert, type LucideIcon } from "lucide-react";
import { overviewTone, type OverviewLevel } from "../../lib/tones";
import { Alert, ButtonLink } from "../../ui";

export type BannerVerdict = {
  level: OverviewLevel;
  sentence: string;
};

const LEVEL_ICONS: Record<OverviewLevel, LucideIcon> = {
  ok: CircleCheck,
  working: Activity,
  attention: TriangleAlert,
  degraded: TriangleAlert,
  down: OctagonAlert,
};

const SEPARATOR = " · ";
const LINKED_LEVELS: ReadonlySet<OverviewLevel> = new Set(["attention", "degraded", "down"]);

function sentenceLines(verdict: BannerVerdict): { primary: string; secondary: string | null } {
  const index = verdict.sentence.indexOf(SEPARATOR);
  if (verdict.level !== "attention" || index === -1) {
    return { primary: verdict.sentence, secondary: null };
  }
  return {
    primary: verdict.sentence.slice(0, index),
    secondary: verdict.sentence.slice(index + SEPARATOR.length),
  };
}

export function VerdictBanner({ verdict }: { verdict: BannerVerdict }) {
  const tone = overviewTone(verdict.level);
  const Icon = LEVEL_ICONS[verdict.level];
  const { primary, secondary } = sentenceLines(verdict);
  return (
    <Alert
      tone={tone}
      icon={Icon}
      label="Overall status"
      size="lg"
      title={primary}
      action={
        LINKED_LEVELS.has(verdict.level) && (
          <ButtonLink to="/system" size="sm">
            See system health
          </ButtonLink>
        )
      }
    >
      {secondary !== null && <p className="m-0 text-sm break-words">{secondary}</p>}
    </Alert>
  );
}
