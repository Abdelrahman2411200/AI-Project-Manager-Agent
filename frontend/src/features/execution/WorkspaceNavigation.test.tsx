import { HttpResponse, http } from "msw";
import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "../../app/App";
import { routes } from "../../app/router";
import { sessionFixture } from "../../test/fixtures";
import { server } from "../../test/server";

function renderRoute(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<App router={router} />);
}

describe("global task and report navigation", () => {
  it("opens My Tasks and explains the active-plan prerequisite", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get("*/api/v1/projects", () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    const view = renderRoute("/my-tasks");

    expect(await screen.findByRole("heading", { name: "My tasks" })).toBeInTheDocument();
    expect(screen.getByText("No active-plan tasks yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reports" })).toHaveAttribute("href", "/reports");
    const results = await axe.run(view.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it("opens the global Reports index and provides the project creation path", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get("*/api/v1/projects", () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    renderRoute("/reports");

    expect(await screen.findByRole("heading", { name: "Reports" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "No projects yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create project" })).toHaveAttribute(
      "href",
      "/projects/new",
    );
    expect(screen.getByRole("link", { name: "My tasks" })).toHaveAttribute(
      "href",
      "/my-tasks",
    );
  });
});
