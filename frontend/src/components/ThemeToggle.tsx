import { useEffect, useState } from "react";
import { Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import { SegmentedControl } from "../ui/SegmentedControl";

export const THEME_STORAGE_KEY = "noc.theme";

export const THEMES = ["auto", "light", "dark"] as const;

export type Theme = (typeof THEMES)[number];

const THEME_LABELS: Record<Theme, string> = {
  auto: "Auto",
  light: "Light",
  dark: "Dark",
};

const THEME_ICONS: Record<Theme, LucideIcon> = {
  auto: Monitor,
  light: Sun,
  dark: Moon,
};

function isTheme(value: string | null): value is Theme {
  return THEMES.some((theme) => theme === value);
}

export function readStoredTheme(): Theme {
  try {
    const stored = sessionStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(stored) ? stored : "auto";
  } catch {
    return "auto";
  }
}

function writeStoredTheme(theme: Theme): void {
  try {
    sessionStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    return;
  }
}

export function applyTheme(theme: Theme): void {
  if (theme === "auto") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", theme);
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readStoredTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  function choose(next: Theme) {
    writeStoredTheme(next);
    setTheme(next);
  }

  return (
    <SegmentedControl
      label="Theme"
      iconOnly
      segments={THEMES.map((option) => ({ value: option, label: THEME_LABELS[option], icon: THEME_ICONS[option] }))}
      value={theme}
      onChange={choose}
    />
  );
}
