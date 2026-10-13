import { HeartPulse, LayoutDashboard, ScrollText, Server, Settings, Siren, X, type LucideIcon } from "lucide-react";
import { NavLink } from "react-router";
import { buttonClass } from "../ui/Button";
import { cx } from "../lib/cx";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  end: boolean;
};

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/incidents", label: "Incidents", icon: Siren, end: false },
  { to: "/servers", label: "Servers", icon: Server, end: false },
  { to: "/system", label: "System", icon: HeartPulse, end: false },
  { to: "/activity", label: "Activity", icon: ScrollText, end: false },
  { to: "/settings", label: "Settings", icon: Settings, end: false },
];

type SidebarProps = {
  open: boolean;
  onClose: () => void;
};

const OPEN_CLASS = "fixed inset-y-0 left-0 z-40 flex w-64 max-w-[80vw]";
const CLOSED_CLASS = "hidden";
const BASE_CLASS =
  "shrink-0 flex-col gap-6 border-r border-border bg-surface p-4 md:sticky md:top-0 md:flex md:h-screen md:w-56";

export function Sidebar({ open, onClose }: SidebarProps) {
  return (
    <aside id="app-sidebar" aria-label="Sidebar" className={cx(open ? OPEN_CLASS : CLOSED_CLASS, BASE_CLASS)}>
      <div className="flex items-center justify-between gap-2">
        <p className="m-0 text-base font-semibold">Multi-Agent NOC</p>
        <button type="button" onClick={onClose} aria-label="Close menu" className={cx(buttonClass({ variant: "ghost", size: "sm" }), "md:hidden")}>
          <X aria-hidden="true" size={16} />
        </button>
      </div>
      <nav aria-label="Main">
        <ul className="m-0 grid list-none gap-1 p-0">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  onClick={onClose}
                  className={({ isActive }) =>
                    cx(
                      "flex items-center gap-2 rounded-control px-2.5 py-2 text-sm hover:bg-surface-2",
                      isActive ? "bg-surface-2 font-semibold text-fg" : "text-muted",
                    )
                  }
                >
                  <Icon aria-hidden="true" size={18} />
                  {item.label}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
