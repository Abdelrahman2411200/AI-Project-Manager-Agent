import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { HttpResponse, http } from "msw";
import { createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "../../app/App";
import { routes } from "../../app/router";
import type {
  AgentRunView,
  RecommendationView,
  ReportSummaryView,
  ReportView,
} from "../../api/types";
import {
  executionBoardFixture,
  ids,
  projectFixture,
  sessionFixture,
} from "../../test/fixtures";
import { server } from "../../test/server";

const recommendationId = "b0000000-0000-4000-8000-000000000001";
const reportId = "c0000000-0000-4000-8000-000000000001";

const recommendation: RecommendationView = {
  id: recommendationId,
  project_id: ids.project,
  version_id: ids.plan,
  snapshot_id: "d0000000-0000-4000-8000-000000000001",
  recommendation_type: "dependency_warning",
  detection_code: "BLOCKED_TASKS",
  why_it_matters: "Recorded blocked work can prevent dependent tasks from becoming ready.",
  suggested_action: "Resolve the recorded blocker before continuing approved work.",
  expected_impact: "Dependency readiness and the forecast can be recalculated.",
  urgency: "high",
  risk: "Unresolved blocking work can delay approved delivery.",
  approval_required: true,
  verification_step: "Confirm TASK-001 is no longer blocked after recalculation.",
  alternatives: ["Continue monitoring without changing the active plan."],
  state: "open",
  explanation_source: "deterministic",
  evidence: [
    {
      id: "e0000000-0000-4000-8000-000000000001",
      entity_type: "task",
      entity_ref: "TASK-001",
      fact_key: "execution_state",
      fact_value: { status: "blocked", reason: "<script>untrusted</script>" },
      captured_at: "2026-07-23T10:00:00Z",
    },
  ],
  latest_decision: null,
  row_version: 1,
  created_at: "2026-07-23T10:00:00Z",
  updated_at: "2026-07-23T10:00:00Z",
};

const reportSummary: ReportSummaryView = {
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
  created_at: "2026-07-23T10:00:00Z",
};

const report: ReportView = {
  ...reportSummary,
  narrative: {
    title: "<script>Weekly status</script>",
    period_summary: "Persisted project facts form this cited summary.",
    progress_statement: {
      text: "Weighted project progress is 25%.",
      evidence_refs: ["METRIC-PROGRESS"],
    },
    completed_items: [],
    blockers: [],
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
    state_hash: `sha256:${"1".repeat(64)}`,
    event_cursor: null,
    evidence: {
      "METRIC-PROGRESS": {
        entity_type: "metric",
        entity_ref: "METRIC-PROGRESS",
        fact_key: "weighted_progress",
        value: { display_percent: "25%" },
      },
    },
    metrics: {
      weighted_progress_display: "25%",
      blocked_task_count: 0,
    },
    completed_refs: [],
    blocker_refs: [],
    risk_refs: [],
    next_action_refs: [],
    health_label: "On track",
    health_rule_codes: ["NO_ADVERSE_RULES"],
    calculation_versions: { monitoring: "monitoring-v1" },
  },
  markdown: "# Stored Markdown",
};

function renderPath(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<App router={router} />);
}

function commonHandlers() {
  server.use(
    http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
    http.get(`*/api/v1/projects/${ids.project}`, () =>
      HttpResponse.json(projectFixture),
    ),
  );
}

describe("grounded monitoring and reporting experience", () => {
  it("shows evidence and records an explicit decision without implying a plan edit", async () => {
    commonHandlers();
    let current = recommendation;
    let headers: Headers | undefined;
    server.use(
      http.get(`*/api/v1/projects/${ids.project}/execution`, () =>
        HttpResponse.json(executionBoardFixture),
      ),
      http.get(`*/api/v1/projects/${ids.project}/recommendations`, () =>
        HttpResponse.json([current]),
      ),
      http.post(
        `*/api/v1/recommendations/${recommendationId}/decisions/accept`,
        ({ request }) => {
          headers = request.headers;
          current = {
            ...current,
            state: "accepted",
            row_version: 2,
            latest_decision: {
              id: "f0000000-0000-4000-8000-000000000001",
              recommendation_id: recommendationId,
              decision: "accept",
              reason: "Proceed with the grounded action.",
              defer_until: null,
              occurred_at: "2026-07-23T10:02:00Z",
            },
          };
          return HttpResponse.json(current);
        },
      ),
    );
    const user = userEvent.setup();
    const view = renderPath(`/projects/${ids.project}/overview`);
    expect(await screen.findByRole("heading", { name: "Recommended actions" })).toBeInTheDocument();
    await user.click(screen.getByText("Inspect 1 evidence fact"));
    expect(screen.getByText(/<script>untrusted<\/script>/)).toBeInTheDocument();
    expect(view.container.querySelector("script")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Accept guidance" }));
    const dialog = screen.getByRole("dialog", { name: "Accept this guidance?" });
    expect(within(dialog).getByText(/does not mutate tasks/i)).toBeInTheDocument();
    await user.type(
      within(dialog).getByLabelText("Reason (optional)"),
      "Proceed with the grounded action.",
    );
    await user.click(within(dialog).getByRole("button", { name: "Record decision" }));
    await waitFor(() => expect(screen.getByText("No actionable recommendations")).toBeInTheDocument());
    expect(headers?.get("if-match")).toBe("1");
    expect(headers?.get("idempotency-key")).toMatch(/^recommendation-accept-/);

    const results = await axe.run(view.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it("generates a report, polls its run, and opens structured evidence", async () => {
    commonHandlers();
    let requestBody: unknown;
    const completedRun: AgentRunView = {
      id: ids.run,
      project_id: ids.project,
      workflow: "reporting",
      status: "completed",
      current_step: "report.persist",
      token_budget: 8000,
      tokens_used: 0,
      cancel_requested: false,
      proposed_plan_version_id: null,
      outcome: { report_id: reportId },
      created_at: "2026-07-23T10:00:00Z",
      updated_at: "2026-07-23T10:01:00Z",
      started_at: "2026-07-23T10:00:00Z",
      completed_at: "2026-07-23T10:01:00Z",
    };
    server.use(
      http.get(`*/api/v1/projects/${ids.project}/reports`, () =>
        HttpResponse.json([reportSummary]),
      ),
      http.post(`*/api/v1/projects/${ids.project}/reports`, async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json(
          { run_id: ids.run, status: "queued", report_id: null, duplicate: false },
          { status: 202 },
        );
      }),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () =>
        HttpResponse.json(completedRun),
      ),
      http.get(`*/api/v1/reports/${reportId}`, () => HttpResponse.json(report)),
    );
    const user = userEvent.setup();
    const view = renderPath(`/projects/${ids.project}/reports`);
    expect(await screen.findByRole("heading", { name: `${projectFixture.name} reports` })).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Period start"));
    await user.type(screen.getByLabelText("Period start"), "2026-07-17");
    await user.clear(screen.getByLabelText("Period end"));
    await user.type(screen.getByLabelText("Period end"), "2026-07-23");
    await user.click(screen.getByRole("button", { name: "Generate report" }));
    await waitFor(() =>
      expect(requestBody).toEqual({
        report_type: "weekly",
        period_start: "2026-07-17",
        period_end: "2026-07-23",
      }),
    );
    expect(await screen.findByRole("heading", { name: "<script>Weekly status</script>" })).toBeInTheDocument();
    expect(view.container.querySelector("script")).toBeNull();
    expect(screen.getByText("Weighted project progress is 25%.")).toBeInTheDocument();
    expect(screen.getAllByText("METRIC-PROGRESS").length).toBeGreaterThan(0);

    const results = await axe.run(view.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });
});
