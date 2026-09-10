"use client";
import { useEffect } from "react";

/**
 * Applies the profile's theme in the browser. "light" and "dark" stamp data-theme on <html> and are
 * remembered in localStorage "theme" (the root layout reads that key before first paint); "system"
 * removes both so prefers-color-scheme decides.
 */
export function ThemeSetter({ theme }: { theme: string }) {
  useEffect(() => {
    const root = document.documentElement;
    try {
      if (theme === "dark" || theme === "light") {
        localStorage.setItem("theme", theme);
        root.dataset.theme = theme;
      } else {
        localStorage.removeItem("theme");
        delete root.dataset.theme;
      }
    } catch {
      // Storage may be unavailable; the attribute alone still themes this page.
      if (theme === "dark" || theme === "light") root.dataset.theme = theme; else delete root.dataset.theme;
    }
  }, [theme]);
  return null;
}
