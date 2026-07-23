import { render, screen } from "@testing-library/react";
import { createMemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { routes } from "./router";

const session = {
  user: { id: "d070c7d4-e602-45cc-afb0-e83ccac65465", email: "owner@example.com", status: "active" },
  expires_at: "2026-07-29T12:00:00Z",
  csrf_token: null,
};

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("application routes", () => {
  it("renders the premium sign-in experience", () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/sign-in"] });
    render(<App router={router} />);

    expect(screen.getByRole("heading", { name: "Sign in to your workspace" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email address")).toHaveAttribute("autocomplete", "email");
    expect(screen.getByRole("button", { name: "Sign in securely" })).toBeInTheDocument();
  });

  it("redirects an unauthenticated project request to sign in", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          type: "about:blank",
          title: "Request failed",
          status: 401,
          code: "http_error",
          detail: "Authentication required.",
          request_id: "test",
          errors: [],
        }, 401),
      ),
    );
    const router = createMemoryRouter(routes, { initialEntries: ["/projects"] });
    render(<App router={router} />);

    expect(await screen.findByRole("heading", { name: "Sign in to your workspace" })).toBeInTheDocument();
  });

  it("renders the owned-project empty state", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(session))
      .mockResolvedValueOnce(jsonResponse({ items: [], next_cursor: null }));
    vi.stubGlobal("fetch", fetchMock);
    const router = createMemoryRouter(routes, { initialEntries: ["/projects"] });
    render(<App router={router} />);

    expect(await screen.findByRole("heading", { name: "Create your first project" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start project intake" })).toHaveAttribute("href", "/projects/new");
    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
  });

  it("renders the guided project creation contract", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(session)));
    const router = createMemoryRouter(routes, { initialEntries: ["/projects/new"] });
    render(<App router={router} />);

    expect(await screen.findByRole("heading", { name: "Create a new project" })).toBeInTheDocument();
    expect(screen.getByLabelText("Project name *")).toBeRequired();
    expect(screen.getByRole("button", { name: "Create project" })).toBeInTheDocument();
  });
});
