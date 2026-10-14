import type { CSSProperties } from "react";
import type { AgentRunView } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { runStatusTone } from "./labels";

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

export function AgentRunsTimeline({ runs }: { runs: AgentRunView[] }) {
  if (runs.length === 0) {
    return <p className="m-0 text-muted">No agent runs recorded.</p>;
  }
  const axis = timelineAxis(runs);

  return (
    <div className="grid gap-3 rounded-card border border-border bg-surface p-4">
      <ol className="m-0 grid list-none gap-3 p-0">
        {timelineBars(runs).map(({ run, left, width }) => (
          <li key={run.id} className="grid gap-2 md:grid-cols-[minmax(0,15rem)_1fr] md:items-center">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <strong className="font-semibold">{run.agent}</strong>
              <Badge tone={runStatusTone(run.status)}>{run.status}</Badge>
              <span className="text-muted">
                rounds {run.rounds}, tool calls {run.tool_calls}, LLM calls {run.llm_calls}
              </span>
              {run.error !== null && <span className="text-critical">{run.error}</span>}
            </div>
            <div className="relative h-3 rounded-control bg-surface-2">
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
          </li>
        ))}
      </ol>
      <div className="flex justify-between gap-2 text-xs text-muted">
        <span>{new Date(axis.start).toLocaleString()}</span>
        <span>{new Date(axis.end).toLocaleString()}</span>
      </div>
    </div>
  );
}
