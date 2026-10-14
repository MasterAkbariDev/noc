import { Activity, CircleCheck, OctagonAlert, TriangleAlert, type LucideIcon } from "lucide-react";
import { Link } from "react-router";
import { cx } from "../../lib/cx";
import { overviewTone, type OverviewLevel, type Tone } from "../../lib/tones";
import { buttonClass } from "../../ui";

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

const BOX_CLASSES: Record<Tone, string> = {
  critical: "border-critical bg-critical-soft",
  warning: "border-warning bg-warning-soft",
  info: "border-info bg-info-soft",
  ok: "border-ok bg-ok-soft",
  neutral: "border-border bg-surface-2",
  unknown: "border-unknown bg-unknown-soft",
};

const ICON_CLASSES: Record<Tone, string> = {
  critical: "text-critical",
  warning: "text-warning",
  info: "text-info",
  ok: "text-ok",
  neutral: "text-muted",
  unknown: "text-unknown",
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
    <section
      aria-label="Overall status"
      className={cx(
        "flex flex-wrap items-center gap-3 rounded-card border p-4",
        BOX_CLASSES[tone],
      )}
    >
      <Icon aria-hidden="true" size={24} strokeWidth={2.25} className={ICON_CLASSES[tone]} />
      <div className="grid min-w-0 flex-1 gap-1">
        <p className="m-0 text-lg font-semibold break-words">{primary}</p>
        {secondary !== null && <p className="m-0 text-sm break-words">{secondary}</p>}
      </div>
      {LINKED_LEVELS.has(verdict.level) && (
        <Link to="/system" className={buttonClass({ size: "sm" })}>
          See system health
        </Link>
      )}
    </section>
  );
}
