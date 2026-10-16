import * as TabsPrimitive from "@radix-ui/react-tabs";
import type { ReactNode } from "react";

export type TabItem = {
  value: string;
  label: string;
  content: ReactNode;
};

type TabsProps = {
  label: string;
  items: TabItem[];
  value: string;
  onValueChange: (value: string) => void;
};

export function Tabs({ label, items, value, onValueChange }: TabsProps) {
  return (
    <TabsPrimitive.Root value={value} onValueChange={onValueChange}>
      <TabsPrimitive.List aria-label={label} className="flex flex-wrap gap-1 rounded-control bg-surface-2 p-1">
        {items.map((item) => (
          <TabsPrimitive.Trigger
            key={item.value}
            value={item.value}
            className="rounded-[0.375rem] px-3.5 py-1.5 text-sm font-medium text-muted transition-colors hover:text-fg data-[state=active]:bg-surface data-[state=active]:text-fg data-[state=active]:shadow-card"
          >
            {item.label}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {items.map((item) => (
        <TabsPrimitive.Content key={item.value} value={item.value} className="page-enter pt-5">
          {item.content}
        </TabsPrimitive.Content>
      ))}
    </TabsPrimitive.Root>
  );
}
