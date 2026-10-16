import { ArrowDown, ArrowUp } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import type { FleetLive, FleetServerLive, LivePoint, ServerSummary } from "../../api/types";
import { cx } from "../../lib/cx";
import { formatRate } from "../../lib/format";
import type { Tone } from "../../lib/tones";
import { EmptyState, StatusDot } from "../../ui";
import { Sparkline } from "../../ui/charts";
import { lastValue, sumSeries } from "../live/range";
import { serverStatusView } from "../servers/serverView";

const SPARK_WIDTH = 120;
const SPARK_COLOR = "var(--ui-accent)";
const WARN_PERCENT = 75;
const CRITICAL_PERCENT = 90;

const VALUE_CLASSES: Record<Tone, string> = {
  critical: "text-critical",
  warning: "text-warning",
  info: "text-info",
  ok: "text-ok",
  neutral: "text-fg",
  unknown: "text-muted",
};

export function percentTone(percent: number | null): Tone {
  if (percent === null) {
    return "unknown";
  }
  if (percent >= CRITICAL_PERCENT) {
    return "critical";
  }
  return percent >= WARN_PERCENT ? "warning" : "neutral";
}

function values(points: LivePoint[]): number[] {
  return points.map(([, value]) => value);
}

function Tile({ label, children, points, max }: { label: string; children: ReactNode; points: LivePoint[]; max?: number }) {
  return (
    <div className="grid min-w-0 content-start gap-1.5 rounded-control bg-surface-2 px-3 py-2.5">
      <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-2">
        <span className="text-sm text-muted">{label}</span>
        <div className="min-w-0 whitespace-nowrap">{children}</div>
      </div>
      {points.length > 1 ? (
        <Sparkline values={values(points)} max={max} color={SPARK_COLOR} width={SPARK_WIDTH} />
      ) : (
        <span aria-hidden="true" className="h-7" />
      )}
    </div>
  );
}

function PercentTile({ label, points }: { label: string; points: LivePoint[] }) {
  const current = lastValue(points);
  return (
    <Tile label={label} points={points} max={100}>
      <span className={cx("text-xl leading-none font-semibold tabular-nums", VALUE_CLASSES[percentTone(current)])}>
        {current === null ? "–" : `${Math.round(current)} %`}
      </span>
      {current === null && <span className="sr-only">No reading</span>}
    </Tile>
  );
}

function NetworkTile({ live }: { live: FleetServerLive }) {
  const incoming = lastValue(live.net_in);
  const outgoing = lastValue(live.net_out);
  return (
    <Tile label="Internet" points={sumSeries(live.net_in, live.net_out)}>
      {incoming === null && outgoing === null ? (
        <span className="text-xl leading-none font-semibold text-muted">–</span>
      ) : (
        <span className="grid justify-items-end text-sm leading-tight font-semibold tabular-nums">
          <span className="inline-flex items-center gap-1">
            <ArrowDown aria-label="In" size={13} className="text-muted" />
            {formatRate(incoming ?? 0)}
          </span>
          <span className="inline-flex items-center gap-1">
            <ArrowUp aria-label="Out" size={13} className="text-muted" />
            {formatRate(outgoing ?? 0)}
          </span>
        </span>
      )}
    </Tile>
  );
}

function hasReadings(live: FleetServerLive): boolean {
  return [live.cpu, live.memory, live.disk, live.net_in, live.net_out].some((points) => points.length > 0);
}

function incidentsText(count: number): string {
  if (count === 0) {
    return "No open incidents";
  }
  return count === 1 ? "1 open incident" : `${count} open incidents`;
}

const EMPTY_LIVE: Omit<FleetServerLive, "name"> = { cpu: [], memory: [], disk: [], net_in: [], net_out: [] };

function ServerLiveCard({ server, live }: { server: ServerSummary; live: FleetServerLive }) {
  const view = serverStatusView(server.status);
  return (
    <article aria-label={server.name} className="lift grid min-w-0 gap-3 rounded-card border border-border bg-surface p-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <Link to={`/servers/${encodeURIComponent(server.id)}`} className="text-lg font-semibold hover:text-accent hover:underline">
          {server.name}
        </Link>
        <StatusDot tone={view.tone} label={view.label} showLabel />
      </header>
      {hasReadings(live) ? (
        <div className="grid grid-cols-2 gap-2">
          <PercentTile label="CPU" points={live.cpu} />
          <PercentTile label="Memory" points={live.memory} />
          <PercentTile label="Disk" points={live.disk} />
          <NetworkTile live={live} />
        </div>
      ) : (
        <p className="m-0 rounded-control bg-surface-2 px-3 py-2.5 text-sm text-muted">No live readings from this server.</p>
      )}
      <p className={cx("m-0 text-sm", server.open_incidents > 0 ? "font-medium text-warning" : "text-muted")}>
        {incidentsText(server.open_incidents)}
        {server.halted && ", automatic fixes paused"}
      </p>
    </article>
  );
}

type ServerLiveGridProps = {
  servers: ServerSummary[];
  live: FleetLive | undefined;
};

export function ServerLiveGrid({ servers, live }: ServerLiveGridProps) {
  if (servers.length === 0) {
    return <EmptyState title="No servers yet." text="Add a server with noc targets add on the NOC server, and it shows up here with live readings." />;
  }
  const byName = new Map((live?.servers ?? []).map((item) => [item.name, item]));
  return (
    <div className="grid gap-3">
      {live !== undefined && !live.available && (
        <p className="m-0 text-sm text-muted">Live readings are not available right now: the NOC cannot reach Prometheus.</p>
      )}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {servers.map((server) => (
          <ServerLiveCard key={server.id} server={server} live={byName.get(server.name) ?? { name: server.name, ...EMPTY_LIVE }} />
        ))}
      </div>
    </div>
  );
}
