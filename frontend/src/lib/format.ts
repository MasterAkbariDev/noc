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

function countAgo(count: number, unit: string): string {
  return `${count} ${unit}${count === 1 ? "" : "s"} ago`;
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
    return countAgo(Math.floor(elapsed / MINUTE_MS), "minute");
  }
  if (elapsed < DAY_MS) {
    return countAgo(Math.floor(elapsed / HOUR_MS), "hour");
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

export function asSentence(text: string): string {
  const trimmed = text.trim();
  if (trimmed === "") {
    return trimmed;
  }
  const capitalised = trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
  return /[.!?…]$/.test(capitalised) ? capitalised : `${capitalised}.`;
}

export function withoutTitle(title: string, text: string): string {
  for (const prefix of [`${title} needs you:`, `${title}:`]) {
    if (text.startsWith(prefix)) {
      return asSentence(text.slice(prefix.length));
    }
  }
  return asSentence(text);
}
