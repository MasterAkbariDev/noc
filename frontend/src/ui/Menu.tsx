import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { ChevronDown, type LucideIcon } from "lucide-react";
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
};

export function Menu({ label, items }: MenuProps) {
  return (
    <DropdownMenuPrimitive.Root modal={false}>
      <DropdownMenuPrimitive.Trigger className={buttonClass({ variant: "secondary", size: "sm" })}>
        {label}
        <ChevronDown aria-hidden="true" size={14} />
      </DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          align="end"
          sideOffset={6}
          className="z-50 min-w-40 rounded-card border border-border bg-surface p-1 shadow-card"
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
