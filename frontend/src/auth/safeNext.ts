const HOME = "/";

function hasControlOrBackslash(value: string): boolean {
  return [...value].some((character) => character.charCodeAt(0) < 32 || character === "\\");
}

export function safeNext(value: string | null): string {
  if (value === null || !value.startsWith("/") || value.startsWith("//")) {
    return HOME;
  }
  if (hasControlOrBackslash(value)) {
    return HOME;
  }
  return value;
}
