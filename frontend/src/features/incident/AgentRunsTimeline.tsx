import type { CSSProperties } from "react";
import type { AgentRunView } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { List, ListItem } from "../../ui/List";
import { agentLabel, runStatusTone } from "./labels";

const MIN_BAR_PERCENT = 0.5;

export type TimelineAxis = {
  start: number;
  end: number;
};

export type TimelineBar = {
  run: AgentRunView;
  left: number;
  width: number;
};

function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, value));
}

export function timelineAxis(runs: AgentRunView[]): TimelineAxis {
  const starts = runs.map((run) => Date.parse(run.started_at));
  const finishedEnds = runs.flatMap((run) => (run.ended_at === null ? [] : [Date.parse(run.ended_at)]));
  return { start: Math.min(...starts), end: Math.max(...starts, ...finishedEnds) };
}

export function timelineBars(runs: AgentRunView[]): TimelineBar[] {
  const axis = timelineAxis(runs);
  const span = Math.max(axis.end - axis.start, 1);

  return runs.map((run) => {
    const start = Date.parse(run.started_at);
    const end = run.ended_at === null ? axis.end : Date.parse(run.ended_at);
    return {
      run,
      left: clampPercent(((start - axis.start) / span) * 100),
      width: Math.max(clampPercent(((end - start) / span) * 100), MIN_BAR_PERCENT),
    };
  });
}

const RUN_STATUS_TEXT = new Map<string, string>([
  ["succeeded", "finished"],
  ["failed", "failed"],
  ["running", "still working"],
]);

export function seconds(ms: number): string {
  return ms < 10_000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms / 1000)} s`;
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

export function runSummary(run: AgentRunView, axisStart: number, axisEnd: number): string {
  const start = Date.parse(run.started_at);
  const end = run.ended_at === null ? axisEnd : Date.parse(run.ended_at);
  return [
    `started after ${seconds(start - axisStart)}`,
    `worked ${seconds(end - start)}`,
    plural(run.tool_calls, "check"),
    plural(run.llm_calls, "AI call"),
  ].join(" · ");
}

export function AgentRunsTimeline({ runs }: { runs: AgentRunView[] }) {
  if (runs.length === 0) {
    return <p className="m-0 text-muted">No agent runs recorded.</p>;
  }
  const axis = timelineAxis(runs);

  return (
    <div className="grid gap-3 rounded-card border border-border bg-surface p-4">
      <p className="m-0 text-sm text-muted">
        Each bar shows when an agent was working, counted from the moment the investigation started. Bars that
        overlap ran at the same time.
      </p>
      <List ordered>
        {timelineBars(runs).map(({ run, left, width }) => (
          <ListItem key={run.id} className="grid gap-2 md:grid-cols-[minmax(0,20rem)_1fr] md:items-center">
            <div className="grid gap-0.5 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <strong className="font-semibold">{agentLabel(run.agent)}</strong>
                <Badge tone={runStatusTone(run.status)}>{RUN_STATUS_TEXT.get(run.status) ?? run.status}</Badge>
              </div>
              <span className="text-xs text-muted">{runSummary(run, axis.start, axis.end)}</span>
              {run.error !== null && <span className="text-critical">{run.error}</span>}
            </div>
            <div dir="ltr" className="relative h-3 rounded-control bg-surface-2">
              <div
                className="timeline-bar absolute inset-y-0 rounded-control bg-accent"
                style={
                  {
                    "--bar-left": `${left}%`,
                    "--bar-width": `${width}%`,
                    left: "var(--bar-left)",
                    width: "var(--bar-width)",
                  } as CSSProperties
                }
              />
            </div>
          </ListItem>
        ))}
      </List>
      <div dir="ltr" className="grid gap-2 text-xs text-muted md:grid-cols-[minmax(0,20rem)_1fr]">
        <span className="hidden md:block" />
        <div className="flex justify-between">
          <span>0 s</span>
          <span>{seconds(axis.end - axis.start)}</span>
        </div>
      </div>
    </div>
  );
}
