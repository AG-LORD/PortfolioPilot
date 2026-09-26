"use client";

import { useSyncExternalStore } from "react";

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

export function ThemeToggle() {
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

  return (
    <button
      type="button"
      className="shell-icon-button"
      onClick={toggle}
      aria-label={theme ? `Switch to ${next} theme` : "Toggle theme"}
      title={theme ? `Switch to ${next} theme` : "Toggle theme"}
    >
      <span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span>
    </button>
  );
}
