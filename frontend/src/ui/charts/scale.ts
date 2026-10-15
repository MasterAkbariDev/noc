const NICE_STEPS = [1, 2, 2.5, 5, 10];
const TICK_COUNT = 4;

export type Scale = { max: number; ticks: number[] };

export function niceScale(maxValue: number): Scale {
  if (!Number.isFinite(maxValue) || maxValue <= 0) {
    return { max: 1, ticks: [0, 1] };
  }
  const rough = maxValue / TICK_COUNT;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const nice = (NICE_STEPS.find((candidate) => candidate * magnitude >= rough) ?? 10) * magnitude;
  const step = Math.max(1, Math.ceil(nice));
  const max = Math.ceil(maxValue / step) * step;
  const ticks: number[] = [];
  for (let value = 0; value <= max + step / 2; value += step) {
    ticks.push(Number(value.toFixed(6)));
  }
  return { max, ticks };
}

export function compactNumber(value: number): string {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function fullNumber(value: number): string {
  return new Intl.NumberFormat("en").format(value);
}

export function labelEvery(count: number, room: number): number {
  return Math.max(1, Math.ceil(count / Math.max(1, room)));
}
