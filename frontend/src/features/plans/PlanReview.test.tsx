import { HttpResponse, http } from "msw";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "../../app/App";
import { routes } from "../../app/router";
import { ids, planFixture, projectFixture, sessionFixture } from "../../test/fixtures";
import { server } from "../../test/server";

function problem(status: number, detail: string) {
  return {
    type: "about:blank",
    title: "Request failed",
    status,
    code: "http_error",
    detail,
    request_id: "phase-7-test",
    errors: [],
  };
}

function useReviewHandlers(plan = planFixture) {
  server.use(
    http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
    http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
    http.get(`*/api/v1/plan-versions/${ids.plan}`, () => HttpResponse.json(plan)),
    http.get(`*/api/v1/projects/${ids.project}/plan-versions`, () =>
      HttpResponse.json([plan]),
    ),
  );
}

function renderReview() {
  const router = createMemoryRouter(routes, {
    initialEntries: [`/projects/${ids.project}/plan/${ids.plan}/review`],
  });
  return render(<App router={router} />);
}

describe("plan review experience", () => {
  it("renders complete provenance, deterministic facts, and accessible review structure", async () => {
    useReviewHandlers();
    const view = renderReview();

    expect(await screen.findByRole("heading", { name: "Review the complete project plan" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Analysis and scope" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Milestones and tasks" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Dependencies" })).toBeInTheDocument();
    expect(screen.getAllByText("AI proposed", { selector: ".source-badge" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Deterministically calculated")).toBeInTheDocument();
    expect(screen.getByText(planFixture.content_hash)).toBeInTheDocument();
    const results = await axe.run(view.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it("reorders milestones with a keyboard action and the exact row version", async () => {
    let requestBody: unknown;
    let ifMatch: string | null = null;
    useReviewHandlers();
    server.use(
      http.patch(
        `*/api/v1/plan-versions/${ids.plan}/milestones/${ids.milestone2}`,
        async ({ request }) => {
          requestBody = await request.json();
          ifMatch = request.headers.get("If-Match");
          return HttpResponse.json({
            item: { ...planFixture.milestones[1], sequence: 1, source: "user", protected: true },
            plan: { ...planFixture, row_version: 8, quality_status: "failed" },
          });
        },
      ),
    );
    const user = userEvent.setup();
    renderReview();
    const moveButton = await screen.findByRole("button", { name: "Move MS-002 earlier" });

    moveButton.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(requestBody).toEqual({ sequence: 1 }));
    expect(ifMatch).toBe(String(planFixture.row_version));
  });

  it("surfaces a recoverable optimistic-concurrency conflict", async () => {
    useReviewHandlers();
    server.use(
      http.patch(
        `*/api/v1/plan-versions/${ids.plan}/tasks/${ids.task1}`,
        () => HttpResponse.json(problem(409, "Plan version changed; reload before editing."), { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderReview();
    const taskHeading = await screen.findByRole("heading", { name: "Build request form" });
    const task = taskHeading.closest("li");
    expect(task).not.toBeNull();
    await user.click(within(task as HTMLElement).getByRole("button", { name: "Lock" }));

    expect(await screen.findByText("The draft changed elsewhere")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load latest draft" })).toBeInTheDocument();
  });

  it("guards keyboard navigation when an editor has unsaved changes", async () => {
    useReviewHandlers();
    const user = userEvent.setup();
    renderReview();
    const taskHeading = await screen.findByRole("heading", { name: "Build request form" });
    const task = taskHeading.closest("li");
    expect(task).not.toBeNull();
    await user.click(within(task as HTMLElement).getByRole("button", { name: "Edit" }));
    const title = screen.getByLabelText("Task title");
    await user.clear(title);
    await user.type(title, "Build the accessible request form");
    const primaryNavigation = screen.getByRole("navigation", { name: "Primary navigation" });
    await user.click(within(primaryNavigation).getByRole("link", { name: "Projects" }));

    expect(screen.getByRole("alertdialog", { name: "Leave this editor?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep editing" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Discard changes" })).toBeInTheDocument();
  });

  it("renders a permission-safe state for an unavailable project", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(
        `*/api/v1/projects/${ids.project}`,
        () => HttpResponse.json(problem(404, "Project not found."), { status: 404 }),
      ),
      http.get(`*/api/v1/plan-versions/${ids.plan}`, () => HttpResponse.json(planFixture)),
      http.get(`*/api/v1/projects/${ids.project}/plan-versions`, () => HttpResponse.json([])),
    );
    renderReview();

    expect(await screen.findByRole("heading", { name: "Plan review unavailable" })).toBeInTheDocument();
    expect(screen.getByText(/does not exist, or your account/)).toBeInTheDocument();
  });
});
