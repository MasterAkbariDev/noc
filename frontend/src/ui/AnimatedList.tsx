import { useEffect, useRef, useState, type ReactNode } from "react";
import { cx } from "../lib/cx";

const LEAVE_MS = 220;

type AnimatedListProps<T> = {
  items: T[];
  itemKey: (item: T) => string;
  render: (item: T) => ReactNode;
  label?: string;
  className?: string;
  itemClassName?: string;
};

type Entry<T> = { item: T; key: string; index: number };

function entriesOf<T>(items: T[], itemKey: (item: T) => string): Entry<T>[] {
  return items.map((item, index) => ({ item, key: itemKey(item), index }));
}

function withLeaving<T>(current: Entry<T>[], leaving: Entry<T>[]): (Entry<T> & { leaving: boolean })[] {
  const merged = current.map((entry) => ({ ...entry, leaving: false }));
  leaving.forEach((entry) => merged.splice(Math.min(entry.index, merged.length), 0, { ...entry, leaving: true }));
  return merged;
}

export function AnimatedList<T>({ items, itemKey, render, label, className, itemClassName }: AnimatedListProps<T>) {
  const current = entriesOf(items, itemKey);
  const signature = current.map((entry) => entry.key).join("\n");
  const firstKeys = useRef(new Set(current.map((entry) => entry.key)));
  const previous = useRef(current);
  const latest = useRef(current);
  latest.current = current;
  const [leaving, setLeaving] = useState<Entry<T>[]>([]);

  useEffect(() => {
    const keys = new Set(latest.current.map((entry) => entry.key));
    const gone = previous.current.filter((entry) => !keys.has(entry.key));
    previous.current = latest.current;
    if (gone.length === 0) {
      return;
    }
    setLeaving(gone);
    const timer = window.setTimeout(() => setLeaving([]), LEAVE_MS);
    return () => window.clearTimeout(timer);
  }, [signature]);

  return (
    <ul aria-label={label} className={cx("m-0 grid list-none p-0", className)}>
      {withLeaving(current, leaving).map((entry) => (
        <li
          key={entry.leaving ? `leaving-${entry.key}` : entry.key}
          aria-hidden={entry.leaving || undefined}
          className={cx(itemClassName, entry.leaving ? "item-leave" : !firstKeys.current.has(entry.key) && "item-enter")}
        >
          {render(entry.item)}
        </li>
      ))}
    </ul>
  );
}
