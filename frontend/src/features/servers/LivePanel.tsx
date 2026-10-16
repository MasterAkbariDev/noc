import type { LivePoint, ServerLive } from "../../api/types";
import { formatRate, formatUptime } from "../../lib/format";
import { DescriptionList, Section, Skeleton } from "../../ui";
import { TimeChart } from "../../ui/charts";
import { useServerLive } from "../live/queries";
import { lastValue, rangeSeconds, useLiveRange } from "../live/range";
import { RangeSelect } from "../live/RangeSelect";

const FIRST = "var(--ui-chart-1)";
const SECOND = "var(--ui-chart-2)";
const LIGHT_LOAD = 0.7;
const FULL_LOAD = 1;

const percentText = (value: number) => `${Math.round(value)} %`;
const loadText = (value: number) => value.toFixed(2);
const errorsText = (value: number) => `${value.toFixed(value < 10 ? 1 : 0)}/s`;

export function loadMeaning(load: number | null, cores: number | null): string {
  if (load === null) {
    return "No reading";
  }
  if (cores === null || cores === 0) {
    return loadText(load);
  }
  const perCore = load / cores;
  const word = perCore < LIGHT_LOAD ? "light" : perCore < FULL_LOAD ? "busy" : "overloaded";
  return `${loadText(load)} on ${cores} ${cores === 1 ? "core" : "cores"}, ${word}`;
}

function LiveFacts({ live }: { live: ServerLive }) {
  return (
    <DescriptionList
      items={[
        {
          key: "uptime",
          term: "Running for",
          detail: live.uptime_seconds === null ? "No reading" : formatUptime(live.uptime_seconds),
        },
        { key: "load", term: "Load now", detail: loadMeaning(lastValue(live.load), live.cpu_count) },
      ]}
    />
  );
}

type ChartsProps = { live: ServerLive; from: number; to: number };

function LiveCharts({ live, from, to }: ChartsProps) {
  const step = live.step_seconds;
  const one = (name: string, points: LivePoint[]) => [{ name, color: FIRST, points }];
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <TimeChart title="CPU" subtitle="How busy the processor is" series={one("CPU", live.cpu)} from={from} to={to} step={step} format={percentText} max={100} />
      <TimeChart title="Memory" subtitle="How much of the memory is in use" series={one("Memory", live.memory)} from={from} to={to} step={step} format={percentText} max={100} />
      <TimeChart title="Disk space" subtitle="The fullest drive" series={one("Disk", live.disk)} from={from} to={to} step={step} format={percentText} max={100} />
      <TimeChart
        title="Internet traffic"
        subtitle="Data coming in and going out"
        series={[
          { name: "In", color: FIRST, points: live.net_in },
          { name: "Out", color: SECOND, points: live.net_out },
        ]}
        from={from}
        to={to}
        step={step}
        format={formatRate}
        empty="No network readings. The server's node_exporter may not report network traffic."
      />
      <TimeChart
        title="Disk speed"
        subtitle="Reading from and writing to the disks"
        series={[
          { name: "Read", color: FIRST, points: live.disk_read },
          { name: "Write", color: SECOND, points: live.disk_write },
        ]}
        from={from}
        to={to}
        step={step}
        format={formatRate}
      />
      <TimeChart
        title="Load"
        subtitle={live.cpu_count === null ? "Work waiting for the processor" : `Work waiting for the processor; ${live.cpu_count} means every core is busy`}
        series={one("Load", live.load)}
        from={from}
        to={to}
        step={step}
        format={loadText}
      />
      <TimeChart
        title="Network errors"
        subtitle="Lost or broken network packets; above zero means a bad connection"
        series={one("Errors", live.net_errors)}
        from={from}
        to={to}
        step={step}
        format={errorsText}
        empty="No network readings. The server's node_exporter may not report network traffic."
      />
    </div>
  );
}

export function LivePanel({ serverId }: { serverId: string }) {
  const [range, setRange] = useLiveRange();
  const query = useServerLive(serverId, range);
  const to = query.dataUpdatedAt > 0 ? query.dataUpdatedAt / 1000 : Date.now() / 1000;
  const from = to - rangeSeconds(query.data?.range ?? range);
  return (
    <Section heading="Live readings" description="Updated on their own while this page is open." actions={<RangeSelect value={range} onChange={setRange} />}>
      {query.data === undefined ? (
        query.isError ? (
          <p className="m-0 text-sm text-muted">Live readings could not be loaded. They are tried again in a moment.</p>
        ) : (
          <Skeleton lines={4} />
        )
      ) : !query.data.available ? (
        <p className="m-0 text-sm text-muted">Live readings are not available right now: the NOC cannot reach Prometheus.</p>
      ) : (
        <div className={query.isPlaceholderData ? "grid gap-4 opacity-60 transition-opacity" : "grid gap-4 transition-opacity"}>
          <LiveFacts live={query.data} />
          <LiveCharts live={query.data} from={from} to={to} />
        </div>
      )}
    </Section>
  );
}

export function useServiceMemory(serverId: string) {
  const [range] = useLiveRange();
  const query = useServerLive(serverId, range);
  return new Map((query.data?.services ?? []).map((service) => [service.resource_id, service]));
}
