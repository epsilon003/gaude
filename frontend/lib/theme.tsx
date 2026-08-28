"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Theme = "light" | "dark";

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

/**
 * The actual class-setting on <html> happens synchronously before hydration
 * via the inline script in app/layout.tsx (avoids a flash of the wrong
 * theme). This provider's job is just to sync React state to whatever class
 * is already there, and to handle toggling afterward.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const initial = document.documentElement.classList.contains("dark") ? "dark" : "light";
    setTheme(initial);
  }, []);

  function toggleTheme() {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      document.documentElement.classList.toggle("dark", next === "dark");
      localStorage.setItem("theme", next);
      return next;
    });
  }

  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return ctx;
}

/**
 * Inline script source, injected via a <script> tag in layout.tsx (not as an
 * imported function — it must run synchronously in <head>, before React
 * hydrates, or there's a visible flash of the default theme on every load).
 */
export const themeInitScript = `
(function() {
  try {
    var stored = localStorage.getItem('theme');
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    var dark = stored ? stored === 'dark' : prefersDark;
    if (dark) document.documentElement.classList.add('dark');
  } catch (e) {}
})();
`;
