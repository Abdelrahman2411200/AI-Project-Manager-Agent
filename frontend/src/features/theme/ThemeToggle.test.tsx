import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "./ThemeProvider";
import { ThemeToggle } from "./ThemeToggle";
import { THEME_STORAGE_KEY } from "./theme";

const matchMedia = vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  addListener: vi.fn(),
  removeListener: vi.fn(),
  dispatchEvent: vi.fn(),
}));

describe("ThemeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
    Object.defineProperty(window, "matchMedia", { configurable: true, value: matchMedia });
  });

  afterEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.removeAttribute("data-theme-preference");
    document.documentElement.removeAttribute("style");
  });

  it("switches to dark theme, persists the choice, and exposes an accessible action", async () => {
    const user = userEvent.setup();
    const view = render(<ThemeProvider><ThemeToggle /></ThemeProvider>);

    const toggle = await screen.findByRole("button", { name: "Switch to dark theme" });
    await user.click(toggle);

    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "dark"));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(screen.getByRole("button", { name: "Switch to light theme" })).toBeVisible();
    const results = await axe.run(view.container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations).toEqual([]);

    view.unmount();
    render(<ThemeProvider><ThemeToggle /></ThemeProvider>);
    expect(await screen.findByRole("button", { name: "Switch to light theme" })).toBeVisible();
  });
});
