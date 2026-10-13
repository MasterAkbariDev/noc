import { useState, type ReactNode } from "react";
import { useLocation } from "react-router";
import { ErrorBoundary } from "./ErrorBoundary";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="min-h-screen md:flex">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-control focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar menuOpen={menuOpen} onToggleMenu={() => setMenuOpen((open) => !open)} />
        <main id="main" tabIndex={-1} className="mx-auto w-full min-w-0 max-w-6xl flex-1 p-4 md:p-6">
          <ErrorBoundary key={location.pathname}>{children}</ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
