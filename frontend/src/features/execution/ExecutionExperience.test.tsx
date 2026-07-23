import { HttpResponse, http } from "msw";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "../../app/App";
import { routes } from "../../app/router";
import type {
  ExecutionBoardView,
  ProjectHealthView,
  TaskExecutionView,
} from "../../api/types";
import {
  executionBoardFixture,
  ids,
  projectFixture,
  sessionFixture,
} from "../../test/fixtures";
import { server } from "../../test/server";

function problem(status: number, detail: string) {
  return {
    type: "about:blank",
    title: "Request failed",
    status,
    code: "execution_error",
    detail,
    request_id: "phase-8-test",
    errors: [],
  };
}

function renderExecution(path = `/projects/${ids.project}/board`) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<App router={router} />);
}

function handlers(board: ExecutionBoardView = executionBoardFixture) {
  let currentBoard = board;
  server.use(
    http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
    http.get(`*/api/v1/projects/${ids.project}`, () =>
      HttpResponse.json(projectFixture),
    ),
    http.get(`*/api/v1/projects/${ids.project}/execution`, () =>
      HttpResponse.json(currentBoard),
    ),
  );
  return (nextBoard: ExecutionBoardView) => {
    currentBoard = nextBoard;
  };
}

function atRiskHealth(reference: string): ProjectHealthView {
  return {
    ...executionBoardFixture.health,
    state_hash: `sha256:${"2".repeat(64)}`,
    label: "At risk",
    rule_codes: ["BLOCKED_CRITICAL_TASK"],
    evidence: [
      {
        rule_code: "BLOCKED_CRITICAL_TASK",
        values: { blocked_count: "1" },
        references: [reference],
      },
    ],
    detections: [
      {
        code: "BLOCKED_TASKS",
        severity: "warning",
        references: [reference],
        values: { blocked_count: "1" },
        calculation_version: "monitoring-v1",
      },
    ],
  };
}

describe("active execution experience", () => {
  it("renders a keyboard-selectable board and list with no serious accessibility violations", async () => {
    handlers();
    const user = userEvent.setup();
    const view = renderExecution();

    expect(
      await screen.findByRole("heading", {
        name: `${projectFixture.name} execution board`,
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "ready" })).toBeInTheDocument();
    expect(screen.getByText("Waiting for TASK-001")).toBeInTheDocument();
    const listButton = screen.getByRole("button", { name: "Accessible list" });
    listButton.focus();
    await user.keyboard("{Enter}");
    expect(listButton).toHaveAttribute("aria-pressed", "true");
    expect(view.container.querySelector(".execution-list")).not.toBeNull();

    const results = await axe.run(view.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it("records a blocker by keyboard and visibly updates deterministic health", async () => {
    let requestHeaders: Headers | undefined;
    let requestBody: unknown;
    const setBoard = handlers();
    server.use(
      http.post(
        `*/api/v1/tasks/${ids.task1}/status`,
        async ({ request }) => {
          requestHeaders = request.headers;
          requestBody = await request.json();
          const task: TaskExecutionView = {
            ...executionBoardFixture.tasks[0],
            status: "blocked",
            blocked_reason: "Waiting for the approved service contract.",
            row_version: 2,
          };
          const health = atRiskHealth("TASK-001");
          setBoard({
            ...executionBoardFixture,
            tasks: executionBoardFixture.tasks.map((item) =>
              item.task_id === task.task_id ? task : item,
            ),
            health,
          });
          return HttpResponse.json({
            task,
            event: {
              ...executionBoardFixture.recent_events[0],
              id: "a0000000-0000-4000-8000-000000000010",
              from_status: "ready",
              to_status: "blocked",
              reason: task.blocked_reason,
              actor_id: ids.user,
              actor_type: "user",
            },
            readiness_changes: [],
            progress: executionBoardFixture.progress,
            health,
          });
        },
      ),
    );
    const user = userEvent.setup();
    renderExecution();
    const heading = await screen.findByRole("heading", { name: "Build request form" });
    const card = heading.closest("article");
    expect(card).not.toBeNull();
    const block = within(card as HTMLElement).getByRole("button", { name: "Block" });
    block.focus();
    await user.keyboard("{Enter}");
    const reason = screen.getByLabelText("Reason *");
    await user.type(reason, "Waiting for the approved service contract.");
    await user.click(screen.getByRole("button", { name: "Confirm blocker" }));

    await waitFor(() =>
      expect(requestBody).toEqual({
        to_status: "blocked",
        reason: "Waiting for the approved service contract.",
      }),
    );
    expect(requestHeaders?.get("if-match")).toBe("1");
    expect(requestHeaders?.get("idempotency-key")).toMatch(
      /^status-blocked-/,
    );
    expect((await screen.findAllByText("At risk")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("BLOCKED_CRITICAL_TASK").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Waiting for the approved service contract."),
    ).toBeInTheDocument();
  });

  it("surfaces a recoverable optimistic concurrency conflict", async () => {
    handlers();
    server.use(
      http.post(`*/api/v1/tasks/${ids.task1}/status`, () =>
        HttpResponse.json(
          problem(409, "Task execution changed concurrently; load the latest state."),
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderExecution();
    const heading = await screen.findByRole("heading", { name: "Build request form" });
    const card = heading.closest("article");
    expect(card).not.toBeNull();
    await user.click(
      within(card as HTMLElement).getByRole("button", { name: "Start task" }),
    );
    await user.click(screen.getByRole("button", { name: "Confirm change" }));

    expect(
      await screen.findByText("This task changed in another session"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load latest task" })).toBeInTheDocument();
  });

  it("shows health rules, entity evidence, forecast, and calculation versions", async () => {
    const board: ExecutionBoardView = {
      ...executionBoardFixture,
      health: atRiskHealth("TASK-001"),
    };
    handlers(board);
    renderExecution(`/projects/${ids.project}/health`);

    expect(
      await screen.findByRole("heading", { name: `${projectFixture.name} health` }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "At risk" })).toBeInTheDocument();
    expect(screen.getAllByText("BLOCKED_CRITICAL_TASK").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "TASK-001" }).length).toBeGreaterThan(0);
    expect(screen.getByText("monitoring: monitoring-v1")).toBeInTheDocument();
  });
});
