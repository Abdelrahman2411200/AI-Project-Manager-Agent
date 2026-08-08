import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  applyTheme,
  resolveTheme,
  storedThemePreference,
  THEME_STORAGE_KEY,
  type ThemePreference,
} from "./theme";
import { ThemeContext } from "./themeContext";
import type { ResolvedTheme } from "./theme";

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>(storedThemePreference);
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => resolveTheme(preference));

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    const synchronize = () => {
      const resolved = resolveTheme(preference);
      setResolvedTheme(resolved);
      applyTheme(preference, resolved);
    };

    synchronize();
    if (preference === "system") media?.addEventListener("change", synchronize);
    return () => media?.removeEventListener("change", synchronize);
  }, [preference]);

  useEffect(() => {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, preference);
    } catch {
      // Theme still works for this session when storage is unavailable.
    }
  }, [preference]);

  const value = useMemo(
    () => ({ preference, resolvedTheme, setPreference }),
    [preference, resolvedTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
