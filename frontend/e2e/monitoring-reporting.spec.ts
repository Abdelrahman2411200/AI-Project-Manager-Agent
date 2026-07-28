import { expect, test, type Page, type Route } from "@playwright/test";

import type {
  AgentRunView,
  RecommendationView,
  ReportSummaryView,
  ReportView,
} from "../src/api/types";
import {
  executionBoardFixture,
  ids,
  projectFixture,
  sessionFixture,
} from "../src/test/fixtures";

const recommendationId = "b0000000-0000-4000-8000-000000000001";
const reportId = "c0000000-0000-4000-8000-000000000001";

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function recommendation(state: RecommendationView["state"]): RecommendationView {
  return {
    id: recommendationId,
    project_id: ids.project,
    version_id: ids.plan,
    snapshot_id: "d0000000-0000-4000-8000-000000000001",
    recommendation_type: "dependency_warning",
    detection_code: "BLOCKED_TASKS",
    why_it_matters: "Recorded blocked work can prevent approved delivery.",
    suggested_action: "Resolve the recorded TASK-002 blocker.",
    expected_impact: "The deterministic schedule can be recalculated.",
    urgency: "high",
    risk: "Unresolved blocking work can delay approved delivery.",
    approval_required: true,
    verification_step: "Confirm TASK-002 is no longer blocked after recalculation.",
    alternatives: ["Continue monitoring without changing the active plan."],
    state,
    explanation_source: "deterministic",
    evidence: [
      {
        id: "e0000000-0000-4000-8000-000000000001",
        entity_type: "task",
        entity_ref: "TASK-002",
        fact_key: "execution_state",
        fact_value: {
          status: "blocked",
          reason: "The external approval contract is unavailable.",
        },
        captured_at: "2026-07-23T10:00:00Z",
      },
    ],
    latest_decision:
      state === "dismissed"
        ? {
            id: "f0000000-0000-4000-8000-000000000001",
            recommendation_id: recommendationId,
            decision: "dismiss",
            reason: "The owner will resolve this outside the current cycle.",
            defer_until: null,
            occurred_at: "2026-07-23T10:02:00Z",
          }
        : null,
    row_version: state === "dismissed" ? 2 : 1,
    created_at: "2026-07-23T10:00:00Z",
    updated_at: "2026-07-23T10:00:00Z",
  };
}

const summary: ReportSummaryView = {
  id: reportId,
  project_id: ids.project,
  version_id: ids.plan,
  run_id: ids.run,
  report_type: "weekly",
  period_start: "2026-07-17",
  period_end: "2026-07-23",
  status: "completed",
  narrative_failure_code: null,
  content_hash: `sha256:${"c".repeat(64)}`,
  created_at: "2026-07-23T10:04:00Z",
};

const detail: ReportView = {
  ...summary,
  narrative: {
    title: "Campus Services factual status",
    period_summary: "Persisted execution events and current state form this report.",
    completed_items: [],
    progress_statement: {
      text: "Weighted project progress is 25%.",
      evidence_refs: ["METRIC-PROGRESS"],
    },
    blockers: [
      {
        text: "TASK-002 is blocked.",
        evidence_refs: ["TASK-002"],
      },
    ],
    risks: [],
    next_actions: [],
    decisions_needed: [],
    caveats: [],
  },
  data: {
    schema_version: "1.0",
    project_id: ids.project,
    project_name: projectFixture.name,
    version_id: ids.plan,
    version_number: 1,
    report_type: "weekly",
    period_start: "2026-07-17",
    period_end: "2026-07-23",
    state_hash: `sha256:${"4".repeat(64)}`,
    event_cursor: "2026-07-23T10:00:00Z:event",
    evidence: {
      "METRIC-PROGRESS": {
        entity_type: "metric",
        entity_ref: "METRIC-PROGRESS",
        fact_key: "weighted_progress",
        value: { display_percent: "25%" },
      },
      "TASK-002": {
        entity_type: "task",
        entity_ref: "TASK-002",
        fact_key: "blocker",
        value: { status: "blocked" },
      },
    },
    metrics: {
      weighted_progress_display: "25%",
      blocked_task_count: 1,
    },
    completed_refs: [],
    blocker_refs: ["TASK-002"],
    risk_refs: [],
    next_action_refs: [],
    health_label: "At risk",
    health_rule_codes: ["BLOCKED_CRITICAL_TASK"],
    calculation_versions: { monitoring: "monitoring-v1" },
  },
  markdown: "# Campus Services factual status\n\nGrounded report.",
};

async function mockInsights(page: Page) {
  let recommendationState: RecommendationView["state"] = "open";
  let reports: ReportSummaryView[] = [];
  const run: AgentRunView = {
    id: ids.run,
    project_id: ids.project,
    workflow: "reporting",
    status: "completed",
    current_step: "report.persist",
    token_budget: 8000,
    tokens_used: 120,
    cancel_requested: false,
    proposed_plan_version_id: null,
    outcome: { report_id: reportId },
    created_at: "2026-07-23T10:03:00Z",
    updated_at: "2026-07-23T10:04:00Z",
    started_at: "2026-07-23T10:03:00Z",
    completed_at: "2026-07-23T10:04:00Z",
  };
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const method = request.method();
    if (path === "/auth/session" && method === "GET") return json(route, sessionFixture);
    if (path === `/projects/${ids.project}` && method === "GET") return json(route, projectFixture);
    if (path === `/projects/${ids.project}/execution` && method === "GET") {
      return json(route, executionBoardFixture);
    }
    if (path === `/projects/${ids.project}/recommendations` && method === "GET") {
      return json(route, [recommendation(recommendationState)]);
    }
    if (
      path === `/recommendations/${recommendationId}/decisions/dismiss` &&
      method === "POST"
    ) {
      expect(request.headers()["if-match"]).toBe("1");
      expect(request.headers()["idempotency-key"]).toMatch(/^recommendation-dismiss-/);
      recommendationState = "dismissed";
      return json(route, recommendation(recommendationState));
    }
    if (path === `/projects/${ids.project}/reports` && method === "GET") {
      return json(route, reports);
    }
    if (path === `/projects/${ids.project}/reports` && method === "POST") {
      expect(request.headers()["idempotency-key"]).toMatch(/^report-/);
      reports = [summary];
      return json(route, {
        run_id: ids.run,
        status: "queued",
        report_id: null,
        duplicate: false,
      }, 202);
    }
    if (path === `/agent-runs/${ids.run}` && method === "GET") return json(route, run);
    if (path === `/reports/${reportId}` && method === "GET") return json(route, detail);
    if (path === `/reports/${reportId}/export.md` && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "text/markdown; charset=utf-8",
        headers: {
          "Content-Disposition": 'attachment; filename="campus-services-weekly-report.md"',
          "Access-Control-Expose-Headers": "Content-Disposition",
          "X-Content-Type-Options": "nosniff",
        },
        body: detail.markdown,
      });
    }
    if (path === `/reports/${reportId}/export.pdf` && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/pdf",
        headers: {
          "Content-Disposition": 'attachment; filename="campus-services-weekly-report.pdf"',
          "Access-Control-Expose-Headers": "Content-Disposition",
          "X-Content-Type-Options": "nosniff",
          "X-Report-Content-Hash": detail.content_hash,
        },
        body: Buffer.from("%PDF-1.7\nphase-12-report\n%%EOF"),
      });
    }
    return json(route, { detail: `Unhandled ${method} ${path}` }, 404);
  });
}

async function expectNoHorizontalOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
}

test("owner decides grounded guidance and exports an immutable factual report", async ({
  page,
}) => {
  await mockInsights(page);
  await page.goto(`/projects/${ids.project}/overview`);
  await expect(page.getByRole("heading", { name: "Recommended actions" })).toBeVisible();
  await page.getByText("Inspect 1 evidence fact").click();
  await expect(page.getByText("The external approval contract is unavailable.")).toBeVisible();
  await page.getByRole("button", { name: "Dismiss" }).click();
  await expect(page.getByText(/does not mutate tasks/i)).toBeVisible();
  await page.getByLabel("Reason (optional)").fill(
    "The owner will resolve this outside the current cycle.",
  );
  await page.getByRole("button", { name: "Record decision" }).click();
  await expect(page.getByText("No actionable recommendations")).toBeVisible();
  await page.reload();
  await expect(page.getByText("No actionable recommendations")).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.getByRole("link", { name: "Reports", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: `${projectFixture.name} reports` }),
  ).toBeVisible();
  await page.getByLabel("Period start").fill("2026-07-17");
  await page.getByLabel("Period end").fill("2026-07-23");
  await page.getByRole("button", { name: "Generate report" }).click();
  await expect(
    page.getByRole("heading", { name: "Campus Services factual status" }),
  ).toBeVisible();
  await expect(page.getByText("Weighted project progress is 25%.")).toBeVisible();
  await expect(page.getByText("TASK-002 is blocked.")).toBeVisible();
  await expect(page.getByText("Evidence index")).toBeVisible();
  await expectNoHorizontalOverflow(page);

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download Markdown" }).click();
  expect((await download).suggestedFilename()).toBe(
    "campus-services-weekly-report.md",
  );
  const pdfDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF" }).click();
  expect((await pdfDownload).suggestedFilename()).toBe(
    "campus-services-weekly-report.pdf",
  );
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Campus Services factual status" }),
  ).toBeVisible();
  await expectNoHorizontalOverflow(page);
});
