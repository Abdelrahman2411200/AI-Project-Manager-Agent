import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { HttpResponse, http } from "msw";
import { createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "../../app/App";
import { routes } from "../../app/router";
import type {
  AdvancedRiskView,
  EvaluationDashboardView,
  PlanGraphView,
  PlanVersionSummary,
} from "../../api/types";
import { ids, planFixture, projectFixture, sessionFixture } from "../../test/fixtures";
import { server } from "../../test/server";
import { buildDependencyGraph } from "./DependencyGraph";
import { ScheduleTimeline } from "./ScheduleTimeline";

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
  fixtures: [
    "ecommerce_six_weeks",
    "football_scouting_eight_weeks",
    "attendance_system",
    "expense_tracker_mobile",
    "incident_investigator",
    "marketing_site_small",
    "analytics_dashboard",
    "impossible_deadline",
  ].map((fixture_id) => ({
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

const initialRisk: AdvancedRiskView = {
  id: "f0000000-0000-4000-8000-000000000001",
  version_id: ids.plan,
  stable_key: "RISK-001",
  category: "schedule",
  description: "The critical delivery path could exceed available capacity.",
  probability: "likely",
  impact: "critical",
  severity: 12,
  trigger: "The deterministic forecast passes the deadline.",
  mitigation: "Review scope and capacity with the project owner.",
  contingency: "Create and approve a replacement plan version.",
  source_fact_refs: ["CONSTRAINT-001"],
  status: "open",
  relations: [
    {
      id: "f0000000-0000-4000-8000-000000000002",
      risk_id: "f0000000-0000-4000-8000-000000000001",
      version_id: ids.plan,
      entity_type: "task",
      entity_ref: "TASK-001",
    },
    {
      id: "f0000000-0000-4000-8000-000000000003",
      risk_id: "f0000000-0000-4000-8000-000000000001",
      version_id: ids.plan,
      entity_type: "milestone",
      entity_ref: "MS-001",
    },
  ],
};

function commonHandlers(plan: PlanGraphView, summaries: PlanVersionSummary[]) {
  server.use(
    http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
    http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
    http.get(`*/api/v1/projects/${ids.project}/plan-versions`, () =>
      HttpResponse.json(summaries),
    ),
    http.get(`*/api/v1/plan-versions/${ids.plan}`, () => HttpResponse.json(plan)),
    http.get("*/api/v1/evaluations/latest", () => HttpResponse.json(evaluation)),
  );
}

function renderPath(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<App router={router} />);
}

describe("Phase 12 full-version experience", () => {
  it("renders graph, table parity, timeline, risk, and evaluation evidence accessibly", async () => {
    const activePlan: PlanGraphView = { ...planFixture, state: "active" };
    commonHandlers(activePlan, [activeSummary]);
    server.use(
      http.get(`*/api/v1/plan-versions/${ids.plan}/risks`, () =>
        HttpResponse.json([initialRisk]),
      ),
    );
    const view = renderPath(`/projects/${ids.project}/intelligence`);

    expect(
      await screen.findByRole("heading", {
        name: `${projectFixture.name} intelligence`,
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Dependency graph" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "Complete dependency edge list" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "Complete planned schedule" }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Critical exposure/)).toBeInTheDocument();
    expect(
      await screen.findByRole("table", {
        name: "Evaluation result by required university fixture",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("8 / 8")).toBeInTheDocument();
    expect(screen.getByText("Active and reviewed plans remain immutable")).toBeInTheDocument();

    const results = await axe.run(view.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it("creates and deletes a draft risk with optimistic version headers", async () => {
    const draftSummary: PlanVersionSummary = {
      ...activeSummary,
      state: "draft",
      reason: "Draft risk review",
    };
    commonHandlers(planFixture, [draftSummary]);
    let riskItems = [initialRisk];
    let createdBody: unknown;
    let createVersion: string | null = null;
    let deleteVersion: string | null = null;
    server.use(
      http.get(`*/api/v1/plan-versions/${ids.plan}/risks`, () =>
        HttpResponse.json(riskItems),
      ),
      http.post(
        `*/api/v1/plan-versions/${ids.plan}/risks`,
        async ({ request }) => {
          createdBody = await request.json();
          createVersion = request.headers.get("if-match");
          const created: AdvancedRiskView = {
            ...initialRisk,
            id: "f0000000-0000-4000-8000-000000000010",
            stable_key: "RISK-002",
            description: "New delivery capacity risk.",
            probability: "possible",
            impact: "high",
            severity: 6,
            trigger: "Forecast passes the delivery target.",
            mitigation: "Review workload with the project owner.",
            contingency: "Approve a revised delivery plan.",
            source_fact_refs: [],
            relations: [],
          };
          riskItems = [...riskItems, created];
          return HttpResponse.json(
            {
              item: created,
              plan_row_version: 8,
              plan_content_hash: `sha256:${"b".repeat(64)}`,
            },
            { status: 201 },
          );
        },
      ),
      http.delete(
        `*/api/v1/plan-versions/${ids.plan}/risks/f0000000-0000-4000-8000-000000000010`,
        ({ request }) => {
          deleteVersion = request.headers.get("if-match");
          riskItems = [initialRisk];
          return HttpResponse.json({
            stable_key: "RISK-002",
            plan_row_version: 9,
            plan_content_hash: `sha256:${"c".repeat(64)}`,
          });
        },
      ),
    );
    const user = userEvent.setup();
    renderPath(`/projects/${ids.project}/intelligence`);

    await user.click(await screen.findByRole("button", { name: "Add risk" }));
    await user.type(screen.getByLabelText("Description"), "New delivery capacity risk.");
    await user.selectOptions(screen.getByLabelText("Probability"), "possible");
    await user.selectOptions(screen.getByLabelText("Impact"), "high");
    await user.type(screen.getByLabelText("Trigger"), "Forecast passes the delivery target.");
    await user.type(
      screen.getByLabelText("Mitigation"),
      "Review workload with the project owner.",
    );
    await user.type(
      screen.getByLabelText("Contingency"),
      "Approve a revised delivery plan.",
    );
    const editor = screen.getByRole("region", { name: "Add risk" });
    await user.click(within(editor).getByRole("button", { name: "Add risk" }));

    expect(await screen.findByText("New delivery capacity risk.")).toBeInTheDocument();
    expect(createVersion).toBe("7");
    expect(createdBody).toMatchObject({
      description: "New delivery capacity risk.",
      probability: "possible",
      impact: "high",
      relations: [],
    });

    await user.click(screen.getByRole("button", { name: "Remove RISK-002" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(screen.queryByText("New delivery capacity risk.")).not.toBeInTheDocument(),
    );
    expect(deleteVersion).toBe("8");
  });

  it("preserves every existing plan relation when editing a risk", async () => {
    const draftSummary: PlanVersionSummary = {
      ...activeSummary,
      state: "draft",
      reason: "Draft relation review",
    };
    commonHandlers(planFixture, [draftSummary]);
    let updateBody: unknown;
    server.use(
      http.get(`*/api/v1/plan-versions/${ids.plan}/risks`, () =>
        HttpResponse.json([initialRisk]),
      ),
      http.patch(
        `*/api/v1/plan-versions/${ids.plan}/risks/${initialRisk.id}`,
        async ({ request }) => {
          updateBody = await request.json();
          return HttpResponse.json({
            item: initialRisk,
            plan_row_version: 8,
            plan_content_hash: `sha256:${"d".repeat(64)}`,
          });
        },
      ),
    );
    const user = userEvent.setup();
    renderPath(`/projects/${ids.project}/intelligence`);

    await user.click(await screen.findByRole("button", { name: "Edit RISK-001" }));
    const selectedRelations = screen.getByRole("list", {
      name: "Selected plan relations",
    });
    expect(within(selectedRelations).getByText("task:TASK-001")).toBeInTheDocument();
    expect(within(selectedRelations).getByText("milestone:MS-001")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save risk" }));

    await waitFor(() =>
      expect(updateBody).toMatchObject({
        relations: [
          { entity_type: "task", entity_ref: "TASK-001" },
          { entity_type: "milestone", entity_ref: "MS-001" },
        ],
      }),
    );
  });

  it("builds the large graph input within the Phase 12 interaction budget", () => {
    const tasks = Array.from({ length: 1_000 }, (_, index) => ({
      ...planFixture.tasks[0],
      id: `task-${index}`,
      stable_key: `TASK-${String(index + 1).padStart(4, "0")}`,
      title: `Scale task ${index + 1}`,
    }));
    const dependencies = Array.from({ length: 1_000 }, (_, index) =>
      [1, 2, 3]
        .filter((offset) => index + offset < 1_000)
        .map((offset) => ({
          ...planFixture.dependencies[0],
          id: `edge-${index}-${offset}`,
          predecessor_id: `task-${index}`,
          successor_id: `task-${index + offset}`,
        })),
    ).flat();
    const largePlan: PlanGraphView = { ...planFixture, tasks, dependencies };

    const started = performance.now();
    const graph = buildDependencyGraph(largePlan);
    const elapsed = performance.now() - started;

    expect(graph.nodes).toHaveLength(1_000);
    expect(graph.edges).toHaveLength(2_994);
    expect(elapsed).toBeLessThan(1_000);
  });

  it("wraps tasks without dependency edges into a readable grid", () => {
    const tasks = Array.from({ length: 18 }, (_, index) => ({
      ...planFixture.tasks[0],
      id: `edge-free-task-${index}`,
      stable_key: `TASK-${String(index + 1).padStart(3, "0")}`,
      title: `Independent task ${index + 1}`,
    }));
    const graph = buildDependencyGraph({ ...planFixture, tasks, dependencies: [] });
    const positions = graph.nodes.map(({ position }) => `${position.x}:${position.y}`);

    expect(new Set(positions).size).toBe(tasks.length);
    expect(new Set(graph.nodes.map(({ position }) => position.x)).size).toBeGreaterThan(1);
    expect(new Set(graph.nodes.map(({ position }) => position.y)).size).toBeLessThan(tasks.length);
  });

  it("keeps the timeline visual structure under reviewed snapshot coverage", () => {
    const view = render(<ScheduleTimeline plan={planFixture} />);
    expect(view.container.innerHTML).toMatchSnapshot();
  });
});
