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

const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB"];

export function formatBytes(bytes: number): string {
  let value = Math.max(0, bytes);
  let unit = 0;
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = value >= 10 || unit === 0 ? 0 : 1;
  return `${value.toFixed(digits)} ${BYTE_UNITS[unit]}`;
}

export function formatRate(bytesPerSecond: number): string {
  return `${formatBytes(bytesPerSecond)}/s`;
}

export function formatUptime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  if (days > 0) {
    return `${days} ${days === 1 ? "day" : "days"} ${hours % 24} h`;
  }
  if (hours > 0) {
    return `${hours} h ${minutes % 60} min`;
  }
  return `${minutes} min`;
}

export function clockTime(seconds: number): string {
  return new Date(seconds * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

