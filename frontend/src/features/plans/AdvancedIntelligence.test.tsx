import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { HttpResponse, http } from "msw";
import { createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "../../app/App";
import { routes } from "../../app/router";
import type { PlanVersionSummary, ScenarioView } from "../../api/types";
import { ids, projectFixture, sessionFixture } from "../../test/fixtures";
import { server } from "../../test/server";

const scenarioId = "e0000000-0000-4000-8000-000000000011";
const activeVersion: PlanVersionSummary = {
  id: ids.plan,
  project_id: ids.project,
  number: 1,
  state: "active",
  based_on_id: null,
  reason: "Approved baseline",
  content_hash: `sha256:${"a".repeat(64)}`,
  quality_status: "passed",
  row_version: 4,
  created_at: "2026-07-23T10:00:00Z",
  updated_at: "2026-07-23T10:00:00Z",
};
const scenario: ScenarioView = {
  id: scenarioId,
  project_id: ids.project,
  baseline_version_id: ids.plan,
  name: "More weekly capacity",
  overrides_json: { capacity_hours_per_week: 45 },
  result_json: {
    baseline: {
      total_effort_hours: "90.00",
      capacity_hours_per_week: "30.00",
      forecast_weeks: "3.00",
      forecast_finish: "2026-08-13",
      deadline_delta_days: -110,
      critical_path_hours: "42.00",
    },
    scenario: {
      total_effort_hours: "90.00",
      capacity_hours_per_week: "45.00",
      forecast_weeks: "2.00",
      forecast_finish: "2026-08-06",
      deadline_delta_days: -117,
      critical_path_hours: "42.00",
    },
    delta: {
      effort_hours: "0.00",
      forecast_finish_days: -7,
      critical_path_hours: "0.00",
      critical_tasks_added: [],
      critical_tasks_removed: [],
    },
    sources: { baseline_version_id: ids.plan },
  },
  explanation_json: {
    summary: "Forecast changes by -7 days; effort changes by 0.00 hours.",
    tradeoffs: [],
    source: "deterministic",
  },
  status: "completed",
  baseline_content_hash: activeVersion.content_hash,
  calculation_version: "advanced-intelligence-v1",
  created_at: "2026-07-28T10:00:00Z",
};

function commonHandlers() {
  server.use(
    http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
    http.get(`*/api/v1/projects/${ids.project}`, () =>
      HttpResponse.json(projectFixture),
    ),
    http.get(`*/api/v1/projects/${ids.project}/plan-versions`, () =>
      HttpResponse.json([activeVersion]),
    ),
  );
}

function renderPath(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<App router={router} />);
}

describe("advanced intelligence experience", () => {
  it("runs a virtual scenario and navigates to a baseline-labelled result", async () => {
    commonHandlers();
    let submitted: unknown;
    let idempotencyKey: string | null = null;
    server.use(
      http.post(`*/api/v1/projects/${ids.project}/scenarios`, async ({ request }) => {
        submitted = await request.json();
        idempotencyKey = request.headers.get("idempotency-key");
        return HttpResponse.json(scenario, { status: 201 });
      }),
      http.get(`*/api/v1/scenarios/${scenarioId}`, () => HttpResponse.json(scenario)),
    );
    const user = userEvent.setup();
    const view = renderPath(`/projects/${ids.project}/scenarios/new`);

    expect(await screen.findByRole("heading", { name: "Run a what-if scenario" })).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Scenario name"));
    await user.type(screen.getByLabelText("Scenario name"), "More weekly capacity");
    await user.clear(screen.getByLabelText("Weekly capacity hours"));
    await user.type(screen.getByLabelText("Weekly capacity hours"), "45");
    await user.click(screen.getByRole("button", { name: "Run virtual scenario" }));

    expect(await screen.findByRole("heading", { name: "More weekly capacity" })).toBeInTheDocument();
    expect(screen.getByText("Baseline remains unchanged")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Baseline and virtual scenario metrics" })).toBeInTheDocument();
    expect(submitted).toEqual({
      name: "More weekly capacity",
      baseline_version_id: ids.plan,
      overrides: { capacity_hours_per_week: 45 },
    });
    expect(idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);
    const results = await axe.run(view.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it("shows permission-safe scenario error state", async () => {
    commonHandlers();
    server.use(
      http.get(`*/api/v1/scenarios/${scenarioId}`, () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Not found",
            status: 404,
            code: "http_error",
            detail: "Advanced intelligence resource not found.",
            request_id: "advanced-test",
            errors: [],
          },
          { status: 404 },
        ),
      ),
    );
    renderPath(`/projects/${ids.project}/scenarios/${scenarioId}`);

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Scenario unavailable" })).toBeInTheDocument(),
    );
    expect(screen.queryByText(scenarioId)).not.toBeInTheDocument();
  });
});
