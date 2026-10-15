import {
  ChartColumn,
  HeartPulse,
  LayoutDashboard,
  Radar,
  ScrollText,
  Server,
  Settings,
  Siren,
  X,
  type LucideIcon,
} from "lucide-react";
import { useContext } from "react";
import { NavLink } from "react-router";
import { cx } from "../lib/cx";
import { StreamConnectedContext } from "../live/useEventStream";
import { IconButton } from "../ui/IconButton";
import { List, ListItem } from "../ui/List";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  end: boolean;
  group: NavGroup;
};

export type NavGroup = "Monitor" | "Insights" | "Administration";

export const NAV_GROUPS: NavGroup[] = ["Monitor", "Insights", "Administration"];

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true, group: "Monitor" },
  { to: "/incidents", label: "Incidents", icon: Siren, end: false, group: "Monitor" },
  { to: "/servers", label: "Servers", icon: Server, end: false, group: "Monitor" },
  { to: "/stats", label: "Metrics", icon: ChartColumn, end: false, group: "Insights" },
  { to: "/activity", label: "Activity", icon: ScrollText, end: false, group: "Insights" },
  { to: "/system", label: "System", icon: HeartPulse, end: false, group: "Administration" },
  { to: "/settings", label: "Settings", icon: Settings, end: false, group: "Administration" },
];

type SidebarProps = {
  open: boolean;
  onClose: () => void;
};

const OPEN_CLASS = "fixed inset-y-0 left-0 z-40 flex w-64 max-w-[80vw] shadow-raised";
const CLOSED_CLASS = "hidden";
const BASE_CLASS =
  "shrink-0 flex-col gap-6 overflow-y-auto border-r border-nav-border bg-nav-bg px-3 py-4 text-nav-fg md:sticky md:top-0 md:flex md:h-screen md:w-60";

function Brand({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex items-center justify-between gap-2 px-2">
      <div className="flex min-w-0 items-center gap-2.5">
        <span aria-hidden="true" className="inline-grid size-9 shrink-0 place-items-center rounded-control bg-nav-accent text-nav-bg">
          <Radar size={20} strokeWidth={2.25} />
        </span>
        <div className="min-w-0">
          <p className="m-0 text-sm leading-tight font-semibold">Multi-Agent NOC</p>
          <p className="m-0 text-xs leading-tight text-nav-muted">Operations console</p>
        </div>
      </div>
      <IconButton label="Close menu" icon={X} variant="nav" onClick={onClose} className="md:hidden" />
    </div>
  );
}

function NavEntry({ item, onClose }: { item: NavItem; onClose: () => void }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onClose}
      className={({ isActive }) =>
        cx(
          "relative flex items-center gap-3 rounded-control px-3 py-2 text-sm transition-colors",
          isActive
            ? "bg-nav-active font-semibold text-nav-fg before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-nav-accent before:content-['']"
            : "text-nav-muted hover:bg-nav-hover hover:text-nav-fg",
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon aria-hidden="true" size={18} className={isActive ? "text-nav-accent" : undefined} />
          {item.label}
        </>
      )}
    </NavLink>
  );
}

function LiveState() {
  const connected = useContext(StreamConnectedContext);
  return (
    <p className="m-0 mt-auto flex items-center gap-2 rounded-control border border-nav-border px-3 py-2 text-xs text-nav-muted">
      <span
        aria-hidden="true"
        className={cx("size-2 rounded-full", connected ? "bg-nav-live motion-safe:animate-pulse" : "bg-nav-muted")}
      />
      {connected ? "Live updates on" : "Live updates paused"}
    </p>
  );
}

export function Sidebar({ open, onClose }: SidebarProps) {
  return (
    <aside id="app-sidebar" aria-label="Sidebar" className={cx(open ? OPEN_CLASS : CLOSED_CLASS, BASE_CLASS)}>
      <Brand onClose={onClose} />
      <nav aria-label="Main" className="grid gap-5">
        {NAV_GROUPS.map((group) => (
          <div key={group} className="grid gap-1">
            <p className="m-0 px-3 text-[11px] font-semibold tracking-wider text-nav-muted uppercase">{group}</p>
            <List gap="xs">
              {NAV_ITEMS.filter((item) => item.group === group).map((item) => (
                <ListItem key={item.to}>
                  <NavEntry item={item} onClose={onClose} />
                </ListItem>
              ))}
            </List>
          </div>
        ))}
      </nav>
      <LiveState />
    </aside>
  );
}
