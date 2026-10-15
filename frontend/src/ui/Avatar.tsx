const INITIALS_LENGTH = 2;

export function initials(name: string): string {
  const parts = name.split(/[\s._-]+/).filter((part) => part.length > 0);
  const letters = parts.length > 1 ? parts.map((part) => part.charAt(0)).join("") : name;
  return letters.slice(0, INITIALS_LENGTH).toUpperCase();
}

export function Avatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden="true"
      className="inline-grid size-7 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent"
    >
      {initials(name)}
    </span>
  );
}
