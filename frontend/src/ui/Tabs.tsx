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
      <TabsPrimitive.List aria-label={label} className="flex flex-wrap gap-1 border-b border-border">
        {items.map((item) => (
          <TabsPrimitive.Trigger
            key={item.value}
            value={item.value}
            className="-mb-px border-b-2 border-transparent px-3 py-2 text-sm font-medium text-muted hover:text-fg data-[state=active]:border-accent data-[state=active]:text-fg"
          >
            {item.label}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {items.map((item) => (
        <TabsPrimitive.Content key={item.value} value={item.value} className="pt-4">
          {item.content}
        </TabsPrimitive.Content>
      ))}
    </TabsPrimitive.Root>
  );
}
