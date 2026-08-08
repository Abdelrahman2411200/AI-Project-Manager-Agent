import { expect, test, type Page, type Route } from "@playwright/test";

import type {
  AdvancedRiskView,
  EvaluationDashboardView,
  PlanGraphView,
  PlanVersionSummary,
} from "../src/api/types";
import {
  ids,
  planFixture,
  projectFixture,
  sessionFixture,
} from "../src/test/fixtures";

const activeSummary: PlanVersionSummary = {
  id: ids.plan,
  project_id: ids.project,
  number: 1,
  state: "active",
  based_on_id: null,
  reason: "Approved baseline",
  content_hash: planFixture.content_hash,
  quality_status: "passed",
  row_version: 7,
  created_at: planFixture.created_at,
  updated_at: planFixture.updated_at,
};
const activePlan: PlanGraphView = { ...planFixture, state: "active" };
const risk: AdvancedRiskView = {
  id: "f0000000-0000-4000-8000-000000000001",
  version_id: ids.plan,
  stable_key: "RISK-001",
  category: "schedule",
  description: "The critical delivery path could exceed available capacity.",
  probability: "likely",
  impact: "critical",
  severity: 12,
  trigger: "The forecast passes the delivery deadline.",
  mitigation: "Review capacity and scope with the owner.",
  contingency: "Create and approve a replacement version.",
  source_fact_refs: ["CONSTRAINT-001"],
  status: "open",
  relations: [],
};
const fixtureNames = [
  "ecommerce_six_weeks",
  "football_scouting_eight_weeks",
  "attendance_system",
  "expense_tracker_mobile",
  "incident_investigator",
  "marketing_site_small",
  "analytics_dashboard",
  "impossible_deadline",
];
const evaluation: EvaluationDashboardView = {
  schema_version: "1.0",
  dataset_version: "university-evaluation-v1",
  dataset_hash: `sha256:${"e".repeat(64)}`,
  fixture_source: "backend/tests/fixtures/evals/mvp_evaluation.jsonl",
  fixture_count: 8,
  pass_count: 8,
  release_status: "passed",
  thresholds: {
    module_coverage: "average >= 0.85 and every fixture >= 0.70",
    missing_task_rate: "<= 0.10",
  },
  summary: {
    module_coverage: 1,
    missing_task_rate: 0,
    task_size_compliance: 1,
    dependency_validity: 1,
    hallucination_rate: 0,
  },
  fixtures: fixtureNames.map((fixture_id) => ({
    fixture_id,
    passed: true,
    metrics: {
      module_coverage: 1,
      missing_task_rate: 0,
      task_size_compliance: 1,
      dependency_validity: 1,
      hallucination_rate: 0,
      schedule_match: true,
    },
  })),
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockFullVersion(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const method = request.method();
    if (path === "/auth/session" && method === "GET") return json(route, sessionFixture);
    if (path === `/projects/${ids.project}` && method === "GET") {
      return json(route, projectFixture);
    }
    if (path === `/projects/${ids.project}/plan-versions` && method === "GET") {
      return json(route, [activeSummary]);
    }
    if (path === `/plan-versions/${ids.plan}` && method === "GET") {
      return json(route, activePlan);
    }
    if (path === `/plan-versions/${ids.plan}/risks` && method === "GET") {
      return json(route, [risk]);
    }
    if (path === "/evaluations/latest" && method === "GET") {
      return json(route, evaluation);
    }
    return json(route, { detail: `Unhandled ${method} ${path}` }, 404);
  });
}

test("full-version intelligence remains accessible and responsive", async ({
  page,
}, testInfo) => {
  await mockFullVersion(page);
  await page.goto(`/projects/${ids.project}/intelligence`);

  await expect(
    page.getByRole("heading", { name: `${projectFixture.name} intelligence` }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dependency graph" })).toBeVisible({
    timeout: 15_000,
  });
  await expect(
    page.getByRole("table", { name: "Complete dependency edge list" }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Complete planned schedule" }),
  ).toBeVisible();
  await expect(page.getByText(/Critical exposure/)).toBeVisible();
  await expect(
    page.getByRole("table", {
      name: "Evaluation result by required university fixture",
    }),
  ).toBeVisible();
  await expect(page.getByText("8 / 8")).toBeVisible();
  await expect(
    page.getByText("Active and reviewed plans remain immutable"),
  ).toBeVisible();

  await page.getByRole("link", { name: "Timeline", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Timeline and Gantt" })).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);

  if (testInfo.project.name === "desktop-keyboard") {
    await expect(page.locator(".timeline-experience")).toHaveScreenshot(
      "phase-12-timeline.png",
      {
        animations: "disabled",
        caret: "hide",
        maxDiffPixelRatio: 0.03,
      },
    );
  }

  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator(".react-flow")).toHaveClass(/dark/);
  await expect(page.locator(".dependency-node").first()).toHaveCSS(
    "background-color",
    "rgb(25, 35, 56)",
  );
  await expect(page.locator(".dependency-node").first()).toHaveCSS(
    "color",
    "rgb(233, 238, 248)",
  );
  await expect(page.locator(".react-flow__minimap")).toHaveCSS(
    "background-color",
    "rgb(25, 35, 56)",
  );
});
