import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { ChevronDown, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "../lib/cx";
import { buttonClass } from "./Button";

export type MenuItem = {
  key: string;
  label: string;
  onSelect: () => void;
  icon?: LucideIcon;
  danger?: boolean;
};

type MenuProps = {
  label: string;
  items: MenuItem[];
  trigger?: ReactNode;
};

export function Menu({ label, items, trigger }: MenuProps) {
  return (
    <DropdownMenuPrimitive.Root modal={false}>
      <DropdownMenuPrimitive.Trigger
        aria-label={trigger === undefined ? undefined : label}
        className={cx(buttonClass({ variant: trigger === undefined ? "secondary" : "ghost", size: "sm" }), trigger !== undefined && "py-1 pl-1")}
      >
        {trigger ?? label}
        <ChevronDown aria-hidden="true" size={14} />
      </DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          align="end"
          sideOffset={6}
          className="z-50 min-w-44 rounded-card border border-border bg-surface p-1 shadow-raised"
        >
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <DropdownMenuPrimitive.Item
                key={item.key}
                onSelect={item.onSelect}
                className={cx(
                  "flex cursor-pointer items-center gap-2 rounded-control px-2.5 py-1.5 text-sm outline-none data-[highlighted]:bg-surface-2",
                  item.danger === true && "text-critical",
                )}
              >
                {Icon !== undefined && <Icon aria-hidden="true" size={14} />}
                {item.label}
              </DropdownMenuPrimitive.Item>
            );
          })}
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}
