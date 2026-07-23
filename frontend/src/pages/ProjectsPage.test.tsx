import { HttpResponse, delay, http } from "msw";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "../app/App";
import { routes } from "../app/router";
import { sessionFixture } from "../test/fixtures";
import { server } from "../test/server";

function renderProjects() {
  const router = createMemoryRouter(routes, { initialEntries: ["/projects"] });
  return render(<App router={router} />);
}

describe("projects dashboard states", () => {
  it("announces its loading skeleton", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get("*/api/v1/projects", async () => {
        await delay(500);
        return HttpResponse.json({ items: [], next_cursor: null });
      }),
    );
    renderProjects();

    expect(await screen.findByText("Loading your projects…")).toBeInTheDocument();
  });

  it("shows a retry action for an API failure", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get("*/api/v1/projects", () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Request failed",
            status: 500,
            code: "http_error",
            detail: "Project service unavailable.",
            request_id: "dashboard-test",
            errors: [],
          },
          { status: 500 },
        ),
      ),
    );
    renderProjects();

    expect(await screen.findByRole("heading", { name: "Your projects are temporarily unavailable." })).toBeInTheDocument();
    expect(screen.getByText("Project service unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
