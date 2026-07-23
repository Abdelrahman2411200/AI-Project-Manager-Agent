import { expect, test, type Page, type Route } from "@playwright/test";

import {
  clarificationFixture,
  ids,
  planFixture,
  projectFixture,
  runFixture,
  runStepsFixture,
  sessionFixture,
} from "../src/test/fixtures";
import type { PlanGraphView } from "../src/api/types";

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockLifecycle(page: Page) {
  let run = { ...runFixture };
  let plan: PlanGraphView = structuredClone(planFixture);

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1", "");
    const method = request.method();

    if (path === "/auth/session" && method === "GET") return json(route, sessionFixture);
    if (path === "/projects" && method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      expect(payload.name).toBe("Campus Services Portal");
      expect(payload.constraints).toEqual([
        {
          constraint_type: "delivery",
          value_json: { text: "No external student data" },
          source: "user",
          confirmed: true,
        },
      ]);
      return json(route, projectFixture, 201);
    }
    if (path === `/projects/${ids.project}` && method === "GET") {
      return json(route, projectFixture);
    }
    if (path === `/projects/${ids.project}/planning-runs` && method === "POST") {
      expect(request.headers()["idempotency-key"]).toBeTruthy();
      return json(route, run, 201);
    }
    if (path === `/agent-runs/${ids.run}` && method === "GET") return json(route, run);
    if (path === `/agent-runs/${ids.run}/steps` && method === "GET") {
      return json(route, runStepsFixture);
    }
    if (path === `/projects/${ids.project}/clarifications` && method === "GET") {
      return json(route, [clarificationFixture]);
    }
    if (path === `/projects/${ids.project}/clarifications` && method === "POST") {
      const payload = request.postDataJSON() as { answers: Array<{ answer: unknown }> };
      expect(payload.answers[0]?.answer).toBe("Facilities");
      run = {
        ...run,
        status: "completed",
        current_step: "await_approval",
        proposed_plan_version_id: ids.plan,
        completed_at: "2026-07-23T10:12:00Z",
      };
      return json(route, {
        run,
        questions: [
          { ...clarificationFixture, status: "answered", answer_json: "Facilities" },
        ],
        resumed: true,
      });
    }
    if (path === `/projects/${ids.project}/plan-versions` && method === "GET") {
      return json(route, [plan]);
    }
    if (path === `/plan-versions/${ids.plan}` && method === "GET") return json(route, plan);
    if (path === `/plan-versions/${ids.plan}/validate` && method === "POST") {
      expect(request.headers()["if-match"]).toBe("7");
      plan = { ...plan, row_version: 8, quality_status: "passed" };
      return json(route, {
        passed: true,
        issues: [],
        warning_codes: [],
        calculation_versions: {
          graph: "1.0",
          priority: "1.0",
          schedule: "1.0",
        },
        content_hash: plan.content_hash,
        row_version: plan.row_version,
      });
    }
    if (path === `/plan-versions/${ids.plan}/submit-review` && method === "POST") {
      expect(request.headers()["if-match"]).toBe("8");
      plan = { ...plan, state: "under_review", row_version: 9 };
      return json(route, plan);
    }
    if (path === `/plan-versions/${ids.plan}/approve` && method === "POST") {
      expect(request.headers()["if-match"]).toBe("9");
      const payload = request.postDataJSON() as { content_hash: string };
      expect(payload.content_hash).toBe(plan.content_hash);
      plan = {
        ...plan,
        state: "active",
        row_version: 10,
        approvals: [
          {
            id: "b0000000-0000-4000-8000-000000000001",
            project_id: ids.project,
            version_id: ids.plan,
            actor_id: ids.user,
            decision: "approved",
            reason: null,
            content_hash: plan.content_hash,
            created_at: "2026-07-23T10:15:00Z",
          },
        ],
      };
      return json(route, plan);
    }
    return json(route, {
      type: "about:blank",
      title: "Unhandled mocked request",
      status: 404,
      code: "unhandled",
      detail: `${method} ${path}`,
      request_id: "playwright",
      errors: [],
    }, 404);
  });
}

async function expectNoHorizontalOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
}

test("owner completes project creation through exact-hash plan approval", async ({ page }) => {
  await mockLifecycle(page);
  await page.goto("/projects/new");

  await expect(page.getByRole("heading", { name: "Create a new project" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.getByLabel("Project name *").focus();
  await page.keyboard.type("Campus Services Portal");
  await page.getByLabel("Goal *").fill(projectFixture.goal);
  await page.getByLabel("Desired outcome").fill(projectFixture.desired_outcome ?? "");
  await page.getByLabel("Required features").fill("Students submit service requests");
  await page.getByLabel("Delivery constraints One constraint per line").fill(
    "No external student data",
  );
  await page.getByRole("button", { name: "Save and start planning" }).click();

  await expect(page.getByRole("heading", { name: projectFixture.name })).toBeVisible();
  await page.getByRole("link", { name: "Answer questions" }).click();
  await expect(page.getByRole("heading", { name: `Clarify ${projectFixture.name}` })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  const assumption = page.getByRole("button", { name: "Use assumption" });
  await assumption.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("radio", { name: "Facilities" })).toBeChecked();
  await page.getByRole("button", { name: "Save answers and resume" }).click();

  await expect(page.getByText("Your draft plan is ready for review")).toBeVisible();
  await page.getByRole("link", { name: "Review draft plan" }).click();
  await expect(page.getByRole("heading", { name: "Review the complete project plan" })).toBeVisible();
  await expect(page.getByText("Deterministically calculated")).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.getByRole("button", { name: "Validate draft" }).click();
  await expect(page.getByRole("heading", { name: "Validation passed" })).toBeVisible();
  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(page.getByText("Review mode is read-only")).toBeVisible();
  await page.getByRole("button", { name: "Review approval details" }).click();
  const confirmation = page.getByRole("checkbox", { name: /I reviewed version 1/ });
  await confirmation.focus();
  await page.keyboard.press("Space");
  await page.getByRole("button", { name: "Approve and activate" }).click();

  await expect(page.getByText("This plan is active")).toBeVisible();
  await expect(page.getByText("active", { exact: true }).first()).toBeVisible();
  await expectNoHorizontalOverflow(page);
});
