import { render, screen } from "@testing-library/react";
import { createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import { routes } from "./router";

describe("application shell", () => {
  it("renders the Phase 1 foundation status", () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/"] });

    render(<App router={router} />);

    expect(
      screen.getByRole("heading", { name: "The engineering foundation is ready." }),
    ).toBeInTheDocument();
    expect(screen.getByText("Phase 1 of 13")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
  });

  it("renders a useful fallback for unknown routes", () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/missing"] });

    render(<App router={router} />);

    expect(
      screen.getByRole("heading", { name: "This workspace view does not exist." }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to overview" })).toHaveAttribute("href", "/");
  });
});
