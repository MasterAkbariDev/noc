import { ApiError } from "../api/client";

export function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

export function formatConfidence(value: number | null): string {
  return value === null ? "-" : value.toFixed(2);
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return "Your session ended. Sign in again.";
  }
  if (error instanceof ApiError && error.status === 404) {
    return "Not found.";
  }
  return error instanceof Error ? error.message : "Request failed.";
}
