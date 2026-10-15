import type { LiHTMLAttributes, ReactNode } from "react";
import { cx } from "../lib/cx";

export type ListVariant = "plain" | "inline" | "divided" | "bullet" | "numbered";
export type ListGap = "xs" | "sm" | "md" | "lg";

const VARIANT_CLASSES: Record<ListVariant, string> = {
  plain: "grid list-none p-0",
  inline: "flex flex-wrap list-none p-0",
  divided: "grid list-none divide-y divide-border p-0 [&>li]:py-3 [&>li:first-child]:pt-0 [&>li:last-child]:pb-0",
  bullet: "grid list-disc pl-5 marker:text-muted",
  numbered: "grid list-decimal pl-5 marker:text-muted",
};

const GAP_CLASSES: Record<ListGap, string> = {
  xs: "gap-1",
  sm: "gap-2",
  md: "gap-3",
  lg: "gap-4",
};

type ListProps = {
  children: ReactNode;
  variant?: ListVariant;
  gap?: ListGap;
  ordered?: boolean;
  label?: string;
  className?: string;
};

export function List({ children, variant = "plain", gap = "md", ordered = false, label, className }: ListProps) {
  const listClass = cx("m-0", VARIANT_CLASSES[variant], variant !== "divided" && GAP_CLASSES[gap], className);
  if (ordered || variant === "numbered") {
    return (
      <ol aria-label={label} className={listClass}>
        {children}
      </ol>
    );
  }
  return (
    <ul aria-label={label} className={listClass}>
      {children}
    </ul>
  );
}

export function ListItem(props: LiHTMLAttributes<HTMLLIElement>) {
  return <li {...props} />;
}

export type DescriptionItem = { term: ReactNode; detail: ReactNode; key: string };

type DescriptionListProps = {
  items: DescriptionItem[];
  layout?: "columns" | "stacked";
  className?: string;
};

export function DescriptionList({ items, layout = "columns", className }: DescriptionListProps) {
  return (
    <dl
      className={cx(
        "m-0 grid text-sm",
        layout === "columns" ? "gap-1 sm:grid-cols-[max-content_minmax(0,1fr)] sm:gap-x-6 sm:gap-y-2" : "gap-1",
        className,
      )}
    >
      {items.map((item) => (
        <div key={item.key} className="contents">
          <dt className={cx("text-muted", layout === "stacked" ? "mt-2 first:mt-0" : "mt-2 first:mt-0 sm:mt-0")}>{item.term}</dt>
          <dd className="m-0 min-w-0 break-words">{item.detail}</dd>
        </div>
      ))}
    </dl>
  );
}
