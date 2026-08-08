import { useTheme } from "./themeContext";

export function ThemeToggle() {
  const { resolvedTheme, setPreference } = useTheme();
  const nextTheme = resolvedTheme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label={`Switch to ${nextTheme} theme`}
      title={`Switch to ${nextTheme} theme`}
      onClick={() => setPreference(nextTheme)}
    >
      <span className="theme-toggle-icon" aria-hidden="true">
        {resolvedTheme === "dark" ? "☀" : "☾"}
      </span>
      <span className="theme-toggle-label">{resolvedTheme === "dark" ? "Light" : "Dark"}</span>
    </button>
  );
}
