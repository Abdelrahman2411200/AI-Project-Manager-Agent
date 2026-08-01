import { HttpResponse, http } from "msw";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

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
  planning_model: "gemma3:4b",
};

function renderRoute(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<App router={router} />);
}

describe("planning and clarification experience", () => {
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
      http.post(`*/api/v1/projects/${ids.project}/planning-runs`, () =>
        HttpResponse.json(
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
        ),
      ),
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
    expect(projectCreations).toBe(1);
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
    expect(screen.getAllByText("Resolve clarifications")).toHaveLength(2);
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
