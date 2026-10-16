import { useLocation } from "react-router";
import { Menu as MenuIcon } from "lucide-react";
import { ThemeToggle } from "../components/ThemeToggle";
import { IconButton } from "../ui/IconButton";
import { StatusPill } from "./StatusPill";
import { UserMenu } from "./UserMenu";

type TopBarProps = {
  menuOpen: boolean;
  onToggleMenu: () => void;
};

export function TopBar({ menuOpen, onToggleMenu }: TopBarProps) {
  const onOverview = useLocation().pathname === "/";
  return (
    <header className="sticky top-0 z-30 flex flex-wrap items-center gap-3 border-b border-border bg-bg/85 px-4 py-2.5 backdrop-blur md:px-8">
      <IconButton
        label="Menu"
        icon={MenuIcon}
        variant="secondary"
        showLabel
        aria-controls="app-sidebar"
        aria-expanded={menuOpen}
        onClick={onToggleMenu}
        className="md:hidden"
      />
      <div className="order-last min-w-0 basis-full sm:order-none sm:flex-1 sm:basis-auto">
        {!onOverview && <StatusPill />}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-3">
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
