import type { CSSProperties } from "react";
import type { AgentRunView } from "../api/types";
import { StatusBadge } from "./StatusBadge";

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
    return <p className="muted">No agent runs recorded.</p>;
  }
  const axis = timelineAxis(runs);

  return (
    <div className="card timeline">
      <ol className="timeline-rows">
        {timelineBars(runs).map(({ run, left, width }) => (
          <li key={run.id} className="timeline-row">
            <div className="timeline-label">
              <strong>{run.agent}</strong>
              <StatusBadge status={run.status} />
              <span className="muted">
                rounds {run.rounds}, tool calls {run.tool_calls}, LLM calls {run.llm_calls}
              </span>
              {run.error !== null && <span className="error">{run.error}</span>}
            </div>
            <div className="timeline-track">
              <div
                className={`timeline-bar timeline-bar-${run.status.toLowerCase()}`}
                style={{ "--bar-left": `${left}%`, "--bar-width": `${width}%` } as CSSProperties}
              />
            </div>
          </li>
        ))}
      </ol>
      <div className="timeline-axis muted">
        <span>{new Date(axis.start).toLocaleString()}</span>
        <span>{new Date(axis.end).toLocaleString()}</span>
      </div>
    </div>
  );
}
