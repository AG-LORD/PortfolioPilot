"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";
import { Button } from "@/components/ui/Button";

type Theme = "light" | "dark";

function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readTheme(): Theme {
  const current = document.documentElement.getAttribute("data-theme");
  return current === "dark" || current === "light" ? current : systemTheme();
}

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}

function useTheme() {
  // null on the server; the inline script in app/layout.tsx has already set data-theme before paint.
  const theme = useSyncExternalStore<Theme | null>(subscribe, readTheme, () => null);
  const next: Theme = theme === "dark" ? "light" : "dark";

  function toggle() {
    document.documentElement.setAttribute("data-theme", next);
    try {
      window.localStorage.setItem("theme", next);
    } catch {
      // Storage can be unavailable; the theme still applies for this page view.
    }
  }

  return { theme, next, toggle };
}

export function ThemeToggle() {
  const { theme, next, toggle } = useTheme();
  return (
    <Button variant="ghost" size="icon" onClick={toggle} aria-label={`Switch to ${next} theme`} title={`Switch to ${next} theme`}>
      {theme === "dark" ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
    </Button>
  );
}

// Full-width variant for the mobile menu.
export function ThemeToggleWide() {
  const { theme, next, toggle } = useTheme();
  return (
    <Button variant="outline" className="mt-2 w-full" onClick={toggle}>
      {theme === "dark" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
      {next === "light" ? "Light mode" : "Dark mode"}
    </Button>
  );
}
