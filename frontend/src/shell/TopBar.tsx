import { Menu as MenuIcon } from "lucide-react";
import { ThemeToggle } from "../components/ThemeToggle";
import { TokenBar } from "../components/TokenBar";
import { cx } from "../lib/cx";
import { buttonClass } from "../ui/Button";
import { StatusPill } from "./StatusPill";
import { UserMenu } from "./UserMenu";

type TopBarProps = {
  menuOpen: boolean;
  onToggleMenu: () => void;
};

export function TopBar({ menuOpen, onToggleMenu }: TopBarProps) {
  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-border bg-surface px-4 py-3">
      <button
        type="button"
        aria-controls="app-sidebar"
        aria-expanded={menuOpen}
        onClick={onToggleMenu}
        className={cx(buttonClass({ variant: "secondary", size: "sm" }), "md:hidden")}
      >
        <MenuIcon aria-hidden="true" size={16} />
        Menu
      </button>
      <div className="min-w-0 flex-1">
        <StatusPill />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <TokenBar />
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
