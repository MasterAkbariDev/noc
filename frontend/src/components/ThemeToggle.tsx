import { useEffect, useState } from "react";

export const THEME_STORAGE_KEY = "noc.theme";

export const THEMES = ["auto", "light", "dark"] as const;

export type Theme = (typeof THEMES)[number];

const THEME_LABELS: Record<Theme, string> = {
  auto: "Auto",
  light: "Light",
  dark: "Dark",
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
    <div className="theme-toggle" role="group" aria-label="Theme">
      {THEMES.map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={theme === option}
          onClick={() => choose(option)}
        >
          {THEME_LABELS[option]}
        </button>
      ))}
    </div>
  );
}
