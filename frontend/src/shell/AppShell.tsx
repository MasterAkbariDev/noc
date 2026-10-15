import { Suspense, useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router";
import { Skeleton } from "../ui/Skeleton";
import { ErrorBoundary } from "./ErrorBoundary";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

const MENU_BUTTON_SELECTOR = 'button[aria-controls="app-sidebar"]';
const SIDEBAR_SELECTOR = "#app-sidebar";

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMenuOpen(false);
        document.querySelector<HTMLButtonElement>(MENU_BUTTON_SELECTOR)?.focus();
      }
    }
    function closeOnOutsidePointer(event: PointerEvent) {
      const target = event.target;
      const insideMenu =
        target instanceof Element &&
        (target.closest(SIDEBAR_SELECTOR) !== null || target.closest(MENU_BUTTON_SELECTOR) !== null);
      if (!insideMenu) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("keydown", closeOnEscape);
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
    };
  }, [menuOpen]);

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
        <main id="main" tabIndex={-1} className="mx-auto w-full min-w-0 max-w-7xl flex-1 p-4 md:p-8">
          <ErrorBoundary key={location.pathname}>
            <Suspense fallback={<Skeleton lines={6} />}>{children}</Suspense>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
