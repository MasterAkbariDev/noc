import { Activity, CircleCheck, OctagonAlert, TriangleAlert, type LucideIcon } from "lucide-react";
import { Link } from "react-router";
import type { Kpis, Verdict } from "../../api/types";
import { cx } from "../../lib/cx";
import { asSentence } from "../../lib/format";
import { overviewTone, type OverviewLevel, type Tone } from "../../lib/tones";
import { ButtonLink, CountUp, RelativeTime } from "../../ui";

const LEVEL_ICONS: Record<OverviewLevel, LucideIcon> = {
  ok: CircleCheck,
  working: Activity,
  attention: TriangleAlert,
  degraded: TriangleAlert,
  down: OctagonAlert,
};

const MARK_CLASSES: Record<Tone, string> = {
  critical: "bg-critical-soft text-critical",
  warning: "bg-warning-soft text-warning",
  info: "bg-info-soft text-info",
  ok: "bg-ok-soft text-ok",
  neutral: "bg-surface-2 text-fg",
  unknown: "bg-unknown-soft text-unknown",
};

const SYSTEM_LEVELS: ReadonlySet<OverviewLevel> = new Set(["degraded", "down"]);

type StatusHeroProps = {
  verdict: Verdict;
  kpis: Kpis;
  updatedAt: string;
};

export function StatusHero({ verdict, kpis, updatedAt }: StatusHeroProps) {
  const tone = overviewTone(verdict.level);
  const Icon = LEVEL_ICONS[verdict.level];
  return (
    <section aria-label="Overall status" className="mb-12 grid gap-6">
      <h1 className="sr-only">Overview</h1>
      <div className="flex items-start gap-4 sm:gap-6">
        <span aria-hidden="true" className={cx("breathe mt-1 inline-grid size-11 shrink-0 place-items-center rounded-full sm:size-14", MARK_CLASSES[tone])}>
          <Icon size={24} strokeWidth={2.25} />
        </span>
        <div className="grid min-w-0 gap-2">
          <p className="m-0 text-[clamp(1.75rem,4.2vw,2.75rem)] leading-[1.08] font-semibold tracking-tight text-balance break-words">
            {asSentence(verdict.sentence)}
          </p>
          {verdict.detail != null && <p className="m-0 max-w-[60ch] text-lg text-muted break-words">{asSentence(verdict.detail)}</p>}
          {SYSTEM_LEVELS.has(verdict.level) && (
            <ButtonLink to="/system" size="sm" className="mt-1">
              See which part
            </ButtonLink>
          )}
        </div>
      </div>
      <HeroFacts kpis={kpis} updatedAt={updatedAt} />
    </section>
  );
}

function HeroFacts({ kpis, updatedAt }: { kpis: Kpis; updatedAt: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-8 gap-y-3 border-t border-border pt-5 sm:ml-20">
      <Fact to="/incidents?filter=resolved" value={kpis.fixed_automatically_today} text="fixed on its own in the last 24 hours" tone="ok" />
      <Fact to="/incidents?filter=needs-you" value={kpis.needs_you} text={kpis.needs_you === 1 ? "needs you" : "need you"} tone={kpis.needs_you > 0 ? "warning" : "neutral"} />
      <Fact to="/servers" value={kpis.servers_up} text={`of ${kpis.servers_total} servers reachable`} tone="neutral" />
      <span className="text-sm text-muted">
        Updated <RelativeTime iso={updatedAt} />
      </span>
    </div>
  );
}

const FACT_NUMBER: Record<Tone, string> = {
  critical: "text-critical",
  warning: "text-warning",
  info: "text-info",
  ok: "text-ok",
  neutral: "text-fg",
  unknown: "text-unknown",
};

function Fact({ to, value, text, tone }: { to: string; value: number; text: string; tone: Tone }) {
  return (
    <Link to={to} className="group inline-flex items-baseline gap-2 rounded-control text-muted hover:text-fg">
      <CountUp value={value} className={cx("text-2xl font-semibold tabular-nums", FACT_NUMBER[tone])} />
      <span className="text-[15px] group-hover:underline group-hover:underline-offset-4">{text}</span>
    </Link>
  );
}
