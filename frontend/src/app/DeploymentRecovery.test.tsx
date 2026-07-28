import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import {
  type PreloadRecoveryEnvironment,
  recoverFromPreloadError,
} from "./chunkRecovery";
import { RouteErrorPage } from "./RouteErrorPage";

function recoveryEnvironment(
  overrides: Partial<PreloadRecoveryEnvironment> = {},
): PreloadRecoveryEnvironment {
  return {
    now: () => 100_000,
    readLastAttempt: () => null,
    writeLastAttempt: vi.fn(),
    reload: vi.fn(),
    ...overrides,
  };
}

describe("deployment recovery", () => {
  it("reloads once when Vite reports a stale dynamically imported chunk", () => {
    const event = new Event("vite:preloadError", { cancelable: true });
    const environment = recoveryEnvironment();

    expect(recoverFromPreloadError(event, environment)).toBe(true);
    expect(event.defaultPrevented).toBe(true);
    expect(environment.writeLastAttempt).toHaveBeenCalledWith("100000");
    expect(environment.reload).toHaveBeenCalledOnce();
  });

  it("does not enter a reload loop when the same chunk fails again", () => {
    const event = new Event("vite:preloadError", { cancelable: true });
    const environment = recoveryEnvironment({
      readLastAttempt: () => "99950",
    });

    expect(recoverFromPreloadError(event, environment)).toBe(false);
    expect(event.defaultPrevented).toBe(false);
    expect(environment.writeLastAttempt).not.toHaveBeenCalled();
    expect(environment.reload).not.toHaveBeenCalled();
  });

  it("allows another recovery after the cooldown has elapsed", () => {
    const event = new Event("vite:preloadError", { cancelable: true });
    const environment = recoveryEnvironment({
      now: () => 200_000,
      readLastAttempt: () => "100000",
    });

    expect(recoverFromPreloadError(event, environment)).toBe(true);
    expect(event.defaultPrevented).toBe(true);
    expect(environment.writeLastAttempt).toHaveBeenCalledWith("200000");
    expect(environment.reload).toHaveBeenCalledOnce();
  });

  it("shows a safe route fallback instead of the router developer error page", async () => {
    function BrokenLazyRoute(): never {
      throw new TypeError(
        "Failed to fetch dynamically imported module: /assets/PlanningPage-old.js",
      );
    }
    const router = createMemoryRouter(
      [
        {
          path: "/",
          element: <BrokenLazyRoute />,
          errorElement: <RouteErrorPage />,
        },
      ],
      { initialEntries: ["/"] },
    );

    render(<RouterProvider router={router} />);

    expect(
      await screen.findByRole("heading", { name: "Reload the latest workspace version" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Unexpected Application Error!")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload latest version" })).toBeInTheDocument();
  });
});
