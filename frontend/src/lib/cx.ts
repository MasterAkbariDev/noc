export function cx(...names: (string | false | null | undefined)[]): string {
  return names.filter((name) => typeof name === "string" && name.length > 0).join(" ");
}
