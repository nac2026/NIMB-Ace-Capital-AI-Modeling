"use client";

// Theme = user preference ("light" | "dark" | "system"). Resolved to an
// actual theme via prefers-color-scheme. Persisted to localStorage under
// THEME_KEY. A tiny inline script in app/layout.tsx sets the attribute
// before first paint to avoid a flash of the wrong theme.

import { createContext, useContext, useEffect, useState, useCallback } from "react";

export type ThemePref = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const THEME_KEY = "nrc.theme";

type Ctx = {
  pref: ThemePref;
  resolved: ResolvedTheme;
  setPref: (p: ThemePref) => void;
  cycle: () => void;
};

const ThemeCtx = createContext<Ctx | null>(null);

function resolve(pref: ThemePref): ResolvedTheme {
  if (pref === "light" || pref === "dark") return pref;
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme: ResolvedTheme) {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.style.colorScheme = theme;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>("dark");
  const [resolved, setResolved] = useState<ResolvedTheme>("dark");

  // Hydrate from localStorage + sync with system changes
  useEffect(() => {
    const stored = (localStorage.getItem(THEME_KEY) as ThemePref | null) ?? "dark";
    setPrefState(stored);
    const r = resolve(stored);
    setResolved(r);
    applyTheme(r);

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    function onChange() {
      if (pref === "system") {
        const r2 = mq.matches ? "dark" : "light";
        setResolved(r2);
        applyTheme(r2);
      }
    }
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  // Intentional: only react to `pref` via the other effect below.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setPref = useCallback((p: ThemePref) => {
    setPrefState(p);
    localStorage.setItem(THEME_KEY, p);
    const r = resolve(p);
    setResolved(r);
    applyTheme(r);
  }, []);

  const cycle = useCallback(() => {
    setPref(pref === "light" ? "dark" : pref === "dark" ? "system" : "light");
  }, [pref, setPref]);

  return (
    <ThemeCtx.Provider value={{ pref, resolved, setPref, cycle }}>
      {children}
    </ThemeCtx.Provider>
  );
}

export function useTheme(): Ctx {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
