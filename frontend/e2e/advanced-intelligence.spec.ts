import { expect, test, type Page, type Route } from "@playwright/test";

import type { PlanVersionSummary, ScenarioView } from "../src/api/types";
import { ids, projectFixture, sessionFixture } from "../src/test/fixtures";

const scenarioId = "e0000000-0000-4000-8000-000000000011";
const active: PlanVersionSummary = {
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
  baseline_content_hash: active.content_hash,
  calculation_version: "advanced-intelligence-v1",
  created_at: "2026-07-28T10:00:00Z",
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockScenario(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const method = request.method();
    if (path === "/auth/session" && method === "GET") return json(route, sessionFixture);
    if (path === `/projects/${ids.project}` && method === "GET") {
      return json(route, projectFixture);
    }
    if (path === `/projects/${ids.project}/plan-versions` && method === "GET") {
      return json(route, [active]);
    }
    if (path === `/projects/${ids.project}/scenarios` && method === "POST") {
      expect(request.headers()["idempotency-key"]).toMatch(/^[0-9a-f-]{36}$/);
      expect(await request.postDataJSON()).toEqual({
        name: "More weekly capacity",
        baseline_version_id: ids.plan,
        overrides: { capacity_hours_per_week: 45 },
      });
      return json(route, scenario, 201);
    }
    if (path === `/scenarios/${scenarioId}` && method === "GET") {
      return json(route, scenario);
    }
    return json(route, { detail: `Unhandled ${method} ${path}` }, 404);
  });
}

test("what-if result stays baseline-labelled and responsive", async ({ page }) => {
  await mockScenario(page);
  await page.goto(`/projects/${ids.project}/scenarios/new`);
  await expect(page.getByRole("heading", { name: "Run a what-if scenario" })).toBeVisible();
  await page.getByLabel("Scenario name").fill("More weekly capacity");
  await page.getByLabel("Weekly capacity hours").fill("45");
  await page.getByRole("button", { name: "Run virtual scenario" }).click();
  await expect(page.getByRole("heading", { name: "More weekly capacity" })).toBeVisible();
  await expect(page.getByText("Baseline remains unchanged")).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Exact baseline and virtual scenario values" }),
  ).toBeVisible();
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
});
