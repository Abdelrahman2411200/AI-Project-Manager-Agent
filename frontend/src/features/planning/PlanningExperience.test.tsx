import { HttpResponse, http } from "msw";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { App } from "../../app/App";
import { routes } from "../../app/router";
import {
  clarificationFixture,
  ids,
  projectFixture,
  runFixture,
  runStepsFixture,
  sessionFixture,
} from "../../test/fixtures";
import { server } from "../../test/server";

const configuredCapabilities = {
  planning_ai_configured: true,
  planning_provider: "ollama",
  planning_model: "llama3.1:8b",
  planning_run_default_token_budget: 100_000,
};

function renderRoute(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<App router={router} />);
}

describe("planning and clarification experience", () => {
  beforeEach(() => {
    server.use(
      http.get("*/api/v1/projects/:projectId/planning-runs/active", () =>
        HttpResponse.json(null),
      ),
    );
  });

  it("blocks planning controls for archived projects", async () => {
    const archivedProject = { ...projectFixture, status: "archived" as const };
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(archivedProject)),
    );
    const view = renderRoute(`/projects/${ids.project}/planning`);

    expect(
      await screen.findByRole("heading", {
        name: "Planning is unavailable for archived projects",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start planning" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose an active project" })).toHaveAttribute(
      "href",
      "/projects",
    );
    const results = await axe.run(view.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it("removes planning entry points from an archived project overview", async () => {
    const archivedProject = { ...projectFixture, status: "archived" as const };
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(archivedProject)),
    );
    renderRoute(`/projects/${ids.project}`);

    expect(await screen.findByRole("heading", { name: projectFixture.name })).toBeInTheDocument();
    expect(screen.getByText("This project is archived")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /start planning/i }),
    ).not.toBeInTheDocument();
  });

  it("preserves a newly created project when planning admission fails", async () => {
    let projectCreations = 0;
    let requestedTokenBudget: number | undefined;
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get("*/api/v1/system/capabilities", () =>
        HttpResponse.json(configuredCapabilities),
      ),
      http.post("*/api/v1/projects", () => {
        projectCreations += 1;
        return HttpResponse.json(projectFixture, { status: 201 });
      }),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.post(`*/api/v1/projects/${ids.project}/planning-runs`, async ({ request }) => {
        requestedTokenBudget = ((await request.json()) as { token_budget: number }).token_budget;
        return HttpResponse.json(
          {
            type: "about:blank",
            title: "Request failed",
            status: 429,
            code: "http_error",
            detail: "Daily AI workflow run limit has been reached.",
            request_id: "test-request",
            errors: [],
          },
          { status: 429 },
        );
      }),
    );
    const user = userEvent.setup();
    renderRoute("/projects/new");

    await user.type(await screen.findByLabelText("Project name *"), projectFixture.name);
    await user.type(screen.getByLabelText("Goal *"), projectFixture.goal);
    await user.click(screen.getByRole("button", { name: "Save and start planning" }));

    expect(
      await screen.findByRole("heading", {
        name: "Turn the project intake into an actionable plan",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Daily AI workflow run limit has been reached.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start planning" })).toBeInTheDocument();
    expect(screen.queryByText(/Planning locally with/i)).not.toBeInTheDocument();
    expect(projectCreations).toBe(1);
    expect(requestedTokenBudget).toBe(100_000);
  });

  it("reopens the active planning run instead of starting a duplicate", async () => {
    let planningStarts = 0;
    const waitingRun = { ...runFixture, status: "waiting_for_user" as const };
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/projects/${ids.project}/planning-runs/active`, () =>
        HttpResponse.json(waitingRun),
      ),
      http.get(`*/api/v1/agent-runs/${ids.run}/steps`, () => HttpResponse.json([])),
      http.post(`*/api/v1/projects/${ids.project}/planning-runs`, () => {
        planningStarts += 1;
        return HttpResponse.json(waitingRun, { status: 201 });
      }),
    );

    renderRoute(`/projects/${ids.project}/planning`);

    expect(
      await screen.findByText("Planning is waiting for your decisions"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Answer questions" })).toHaveAttribute(
      "href",
      `/projects/${ids.project}/clarify?run=${ids.run}`,
    );
    expect(planningStarts).toBe(0);
  });

  it("explains the missing provider when an admitted run fails", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get("*/api/v1/system/capabilities", () =>
        HttpResponse.json({
          ...configuredCapabilities,
          planning_ai_configured: false,
          planning_provider: "none",
          planning_model: null,
        }),
      ),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () =>
        HttpResponse.json({
          ...runFixture,
          status: "failed",
          outcome: {
            failure_code: "AI_UNCONFIGURED",
            failed_step: "validate_request",
            recoverable: false,
          },
          completed_at: "2026-07-23T10:02:00Z",
        }),
      ),
      http.get(`*/api/v1/agent-runs/${ids.run}/steps`, () => HttpResponse.json([])),
    );
    renderRoute(`/projects/${ids.project}/planning?run=${ids.run}`);

    expect(
      await screen.findByText(
        "The local model provider is not configured. Start Ollama and restart the API and worker before starting another planning run.",
      ),
    ).toBeInTheDocument();
  });

  it("explains exhausted provider quota without suggesting an immediate retry", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () =>
        HttpResponse.json({
          ...runFixture,
          status: "failed",
          outcome: {
            failure_code: "MODEL_QUOTA_EXHAUSTED",
            failed_step: "detect_gaps",
            recoverable: false,
          },
          completed_at: "2026-07-23T10:02:00Z",
        }),
      ),
      http.get(`*/api/v1/agent-runs/${ids.run}/steps`, () => HttpResponse.json([])),
    );
    renderRoute(`/projects/${ids.project}/planning?run=${ids.run}`);

    expect(
      await screen.findByText(
        "The configured hosted provider has no available quota. Local Ollama runs do not require API credits.",
      ),
    ).toBeInTheDocument();
  });

  it("shows quality-gate reasons and offers a corrected new run", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get("*/api/v1/system/capabilities", () =>
        HttpResponse.json(configuredCapabilities),
      ),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () =>
        HttpResponse.json({
          ...runFixture,
          status: "failed",
          current_step: "quality_gate",
          outcome: {
            failure_code: "QUALITY_GATE_FAILED",
            failed_step: "quality_gate",
            recoverable: false,
          },
          completed_at: "2026-07-23T10:02:00Z",
        }),
      ),
      http.get(`*/api/v1/agent-runs/${ids.run}/steps`, () =>
        HttpResponse.json([
          {
            ...runStepsFixture[0],
            name: "quality_gate",
            status: "failed",
            failure_code: "QUALITY_GATE_FAILED",
            validation: [
              {
                code: "REQUIREMENT_COVERAGE_GAP",
                message: "Every in-scope requirement must be covered by a module or task.",
                references: ["REQ-011", "REQ-014"],
              },
            ],
          },
        ]),
      ),
    );
    renderRoute(`/projects/${ids.project}/planning?run=${ids.run}`);

    expect(
      await screen.findByText(
        "The generated draft omitted or contradicted confirmed project requirements. Review the failed check below; no incomplete plan was saved or activated.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Every in-scope requirement must be covered by a module or task."),
    ).toBeInTheDocument();
    expect(screen.getByText("REQ-011, REQ-014")).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Start a new planning run" }),
    ).toBeEnabled();
  });

  it("allows a terminal partial checkpoint to start a replacement run", async () => {
    const replacementId = "10000000-0000-4000-8000-000000000098";
    let planningStarts = 0;
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () =>
        HttpResponse.json({
          ...runFixture,
          status: "partial",
          outcome: {
            failure_code: "MODEL_BUDGET_EXHAUSTED",
            failed_step: "draft_tasks",
            recoverable: true,
          },
        }),
      ),
      http.get(`*/api/v1/agent-runs/${ids.run}/steps`, () => HttpResponse.json([])),
      http.post(`*/api/v1/projects/${ids.project}/planning-runs`, () => {
        planningStarts += 1;
        return HttpResponse.json(
          { ...runFixture, id: replacementId, status: "queued" },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderRoute(`/projects/${ids.project}/planning?run=${ids.run}`);

    await user.click(
      await screen.findByRole("button", { name: "Start a new planning run" }),
    );

    await waitFor(() => expect(planningStarts).toBe(1));
    expect(await screen.findByText("Planning run queued safely")).toBeInTheDocument();
  });

  it("prevents a new planning run when the provider is not configured", async () => {
    let planningStarts = 0;
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get("*/api/v1/system/capabilities", () =>
        HttpResponse.json({
          ...configuredCapabilities,
          planning_ai_configured: false,
          planning_provider: "none",
          planning_model: null,
        }),
      ),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.post(`*/api/v1/projects/${ids.project}/planning-runs`, () => {
        planningStarts += 1;
        return HttpResponse.json(runFixture, { status: 201 });
      }),
    );
    renderRoute(`/projects/${ids.project}/planning`);

    expect(
      await screen.findByText("AI planning needs server configuration"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "AI planning unavailable" })).toBeDisabled();
    expect(planningStarts).toBe(0);
  });

  it("offers a fresh run after the provider is configured", async () => {
    const recoveredRunId = "10000000-0000-4000-8000-000000000099";
    let planningStarts = 0;
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get("*/api/v1/system/capabilities", () =>
        HttpResponse.json(configuredCapabilities),
      ),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () =>
        HttpResponse.json({
          ...runFixture,
          status: "failed",
          outcome: {
            failure_code: "AI_UNCONFIGURED",
            failed_step: "validate_request",
            recoverable: false,
          },
          completed_at: "2026-07-23T10:02:00Z",
        }),
      ),
      http.get(`*/api/v1/agent-runs/${ids.run}/steps`, () => HttpResponse.json([])),
      http.post(`*/api/v1/projects/${ids.project}/planning-runs`, () => {
        planningStarts += 1;
        return HttpResponse.json(
          {
            ...runFixture,
            id: recoveredRunId,
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderRoute(`/projects/${ids.project}/planning?run=${ids.run}`);

    expect(
      await screen.findByText(
        "The model provider is now configured. This failed run remains as an audit record; start a new planning run to continue.",
      ),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start a new planning run" }));

    await waitFor(() => expect(planningStarts).toBe(1));
    expect(await screen.findByText("Planning is waiting for your decisions")).toBeInTheDocument();
  });

  it("keeps project-only creation available when AI planning is unavailable", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get("*/api/v1/system/capabilities", () =>
        HttpResponse.json({
          ...configuredCapabilities,
          planning_ai_configured: false,
          planning_provider: "none",
          planning_model: null,
        }),
      ),
    );
    renderRoute("/projects/new");

    expect(
      await screen.findByText("AI planning needs server configuration"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "AI planning unavailable" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save project" })).toBeEnabled();
  });

  it("shows concise accessible run progress without raw model details", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () => HttpResponse.json(runFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}/steps`, () =>
        HttpResponse.json(runStepsFixture),
      ),
    );
    const view = renderRoute(`/projects/${ids.project}/planning?run=${ids.run}`);

    expect(await screen.findByRole("heading", { name: projectFixture.name })).toBeInTheDocument();
    expect(screen.getByText("Check project intake")).toBeInTheDocument();
    expect(screen.getAllByText("Resolve clarifications").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("Internal purpose not rendered")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Answer questions" })).toHaveAttribute(
      "href",
      `/projects/${ids.project}/clarify?run=${ids.run}`,
    );
    const results = await axe.run(view.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it("renders a live seven-stage workflow with elapsed time and safe activity", async () => {
    const now = Date.now();
    const completedNames = [
      "validate_request",
      "detect_gaps",
      "wait_or_assume",
      "analyze_project",
      "draft_modules",
      "draft_milestones",
    ];
    const durations = [1_000, 42_000, 1_000, 41_000, 46_000, 62_000];
    const completedSteps = completedNames.map((name, index) => ({
      ...runStepsFixture[0],
      id: `a0000000-0000-4000-8000-${String(index + 20).padStart(12, "0")}`,
      name,
      status: "completed",
      started_at: new Date(now - 197_000 + index * 20_000).toISOString(),
      completed_at: new Date(now - 196_000 + index * 20_000).toISOString(),
      duration_ms: durations[index],
    }));
    const runningStep = {
      ...runStepsFixture[0],
      id: "a0000000-0000-4000-8000-000000000099",
      name: "draft_tasks",
      status: "running",
      started_at: new Date(now - 17_000).toISOString(),
      completed_at: null,
      duration_ms: null,
    };
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () =>
        HttpResponse.json({
          ...runFixture,
          status: "running",
          current_step: "draft_tasks",
          tokens_used: 18_742,
          token_budget: 100_000,
          started_at: new Date(now - 197_000).toISOString(),
          updated_at: new Date(now).toISOString(),
        }),
      ),
      http.get(`*/api/v1/agent-runs/${ids.run}/steps`, () =>
        HttpResponse.json([...completedSteps, runningStep]),
      ),
    );

    const view = renderRoute(`/projects/${ids.project}/planning?run=${ids.run}`);

    expect(await screen.findByText("6 of 7 steps complete")).toBeInTheDocument();
    expect(screen.getAllByText("86%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Live updates")).toBeInTheDocument();
    expect(screen.getByText("Creating actionable, estimable tasks for every milestone.")).toBeInTheDocument();
    expect(screen.getByText("18,742 / 100,000 tokens")).toBeInTheDocument();
    expect(screen.getByLabelText("Draft actionable tasks activity")).toBeInTheDocument();
    expect(screen.queryByText("Internal purpose not rendered")).not.toBeInTheDocument();
    const results = await axe.run(view.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it("shows skipped and cancelled stages without losing pending work", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () =>
        HttpResponse.json({
          ...runFixture,
          status: "cancelled",
          current_step: "analyze_project",
          completed_at: "2026-07-23T10:02:30Z",
        }),
      ),
      http.get(`*/api/v1/agent-runs/${ids.run}/steps`, () =>
        HttpResponse.json([
          runStepsFixture[0],
          {
            ...runStepsFixture[0],
            id: "a0000000-0000-4000-8000-000000000088",
            name: "wait_or_assume",
            status: "skipped",
          },
        ]),
      ),
    );

    renderRoute(`/projects/${ids.project}/planning?run=${ids.run}`);

    expect(await screen.findByRole("heading", { name: "Planning run cancelled" })).toBeInTheDocument();
    expect(screen.getByText(/^Skipped/)).toBeInTheDocument();
    expect(screen.getAllByText("Cancelled").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Pending").length).toBeGreaterThanOrEqual(1);
  });

  it("reports every owner-facing stage complete for a persisted legacy demo run", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () =>
        HttpResponse.json({
          ...runFixture,
          status: "completed",
          current_step: "plan.persist_draft",
          proposed_plan_version_id: ids.plan,
          completed_at: "2026-07-23T10:12:00Z",
        }),
      ),
      http.get(`*/api/v1/agent-runs/${ids.run}/steps`, () =>
        HttpResponse.json(runStepsFixture),
      ),
    );

    renderRoute(`/projects/${ids.project}/planning?run=${ids.run}`);

    expect(await screen.findByText("7 of 7 steps complete")).toBeInTheDocument();
    expect(screen.getAllByText("100%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Save the plan draft")).toBeInTheDocument();
  });

  it("explains a safely persisted queued run without exposing provider details", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () =>
        HttpResponse.json({
          ...runFixture,
          status: "queued",
          current_step: "validate_request",
          started_at: null,
        }),
      ),
      http.get(`*/api/v1/agent-runs/${ids.run}/steps`, () => HttpResponse.json([])),
    );

    renderRoute(`/projects/${ids.project}/planning?run=${ids.run}`);

    expect(await screen.findByText("Planning run queued safely")).toBeInTheDocument();
    expect(screen.getByText(/waiting for an available planning worker/i)).toBeInTheDocument();
    expect(screen.queryByText(/ollama|llama3\.1/i)).not.toBeInTheDocument();
  });

  it("supports keyboard assumption acceptance and submits typed answers", async () => {
    let submitted: unknown;
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () => HttpResponse.json(runFixture)),
      http.get(`*/api/v1/projects/${ids.project}/clarifications`, () =>
        HttpResponse.json([clarificationFixture]),
      ),
      http.post(`*/api/v1/projects/${ids.project}/clarifications`, async ({ request }) => {
        submitted = await request.json();
        return HttpResponse.json({
          run: runFixture,
          questions: [{ ...clarificationFixture, status: "answered", answer_json: "Facilities" }],
          resumed: false,
        });
      }),
    );
    const user = userEvent.setup();
    const view = renderRoute(`/projects/${ids.project}/clarify?run=${ids.run}`);

    expect(await screen.findByRole("heading", { name: `Clarify ${projectFixture.name}` })).toBeInTheDocument();
    const assumption = screen.getByRole("button", { name: "Use assumption" });
    assumption.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("radio", { name: "Facilities" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Save answers and resume" }));
    await waitFor(() =>
      expect(submitted).toEqual({
        run_id: ids.run,
        answers: [{ question_id: ids.question, answer: "Facilities" }],
      }),
    );
    expect(screen.getByText("Draft answers saved in this browser")).toBeInTheDocument();
    const results = await axe.run(view.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });
});
