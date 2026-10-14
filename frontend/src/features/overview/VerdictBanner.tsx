import { CircleCheck, OctagonAlert, TriangleAlert, type LucideIcon } from "lucide-react";
import type { Verdict, VerdictLevel } from "../../api/types";
import { cx } from "../../lib/cx";
import type { Tone } from "../../lib/tones";
import { verdictTone } from "./model";

const LEVEL_ICONS: Record<VerdictLevel, LucideIcon> = {
  ok: CircleCheck,
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

export function VerdictBanner({ verdict }: { verdict: Verdict }) {
  const tone = verdictTone(verdict.level);
  const Icon = LEVEL_ICONS[verdict.level];
  return (
    <section
      aria-label="Overall status"
      className={cx("flex items-center gap-3 rounded-card border p-4", BOX_CLASSES[tone])}
    >
      <Icon aria-hidden="true" size={24} strokeWidth={2.25} className={ICON_CLASSES[tone]} />
      <p className="m-0 text-lg font-semibold">{verdict.sentence}</p>
    </section>
  );
}
