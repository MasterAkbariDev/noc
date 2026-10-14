import { ApiError } from "../api/client";

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return "Your session ended. Sign in again.";
  }
  if (error instanceof ApiError && error.status === 404) {
    return "Not found.";
  }
  return error instanceof Error ? error.message : "Request failed.";
}

export function relativeTime(iso: string, now: Date = new Date()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) {
    return iso;
  }
  const elapsed = now.getTime() - then;
  if (elapsed < MINUTE_MS) {
    return "just now";
  }
  if (elapsed < HOUR_MS) {
    return `${Math.floor(elapsed / MINUTE_MS)} min ago`;
  }
  if (elapsed < DAY_MS) {
    return `${Math.floor(elapsed / HOUR_MS)} h ago`;
  }
  const days = Math.floor(elapsed / DAY_MS);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

export function absoluteTime(iso: string): string {
  const time = new Date(iso);
  return Number.isNaN(time.getTime()) ? iso : time.toLocaleString();
}

export function percentFromFraction(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

export function percentFromHundred(value: number): string {
  return `${Math.round(value)}%`;
}

export function durationMs(ms: number): string {
  const safe = Math.max(0, ms);
  if (safe < 1_000) {
    return `${Math.round(safe)} ms`;
  }
  if (safe < MINUTE_MS) {
    return `${(safe / 1_000).toFixed(1)} s`;
  }
  const totalSeconds = Math.round(safe / 1_000);
  return `${Math.floor(totalSeconds / 60)} min ${totalSeconds % 60} s`;
}
