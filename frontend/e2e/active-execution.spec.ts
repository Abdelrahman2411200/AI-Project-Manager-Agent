import { expect, test, type Page, type Route } from "@playwright/test";

import type {
  ExecutionBoardView,
  TaskExecutionView,
  TaskStatus,
  TaskStatusEventView,
} from "../src/api/types";
import {
  executionBoardFixture,
  ids,
  projectFixture,
  sessionFixture,
} from "../src/test/fixtures";

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function event(
  task: TaskExecutionView,
  fromStatus: TaskStatus,
  toStatus: TaskStatus,
  reason: string,
  sequence: number,
): TaskStatusEventView {
  return {
    id: `a0000000-0000-4000-8000-${sequence.toString().padStart(12, "0")}`,
    project_id: ids.project,
    version_id: ids.plan,
    task_id: task.task_id,
    actor_id: ids.user,
    actor_type: "user",
    from_status: fromStatus,
    to_status: toStatus,
    reason,
    progress_fraction: task.progress_fraction,
    correlation_id: "playwright-execution",
    occurred_at: `2026-08-03T08:0${sequence}:00Z`,
  };
}

function withTask(
  board: ExecutionBoardView,
  taskId: string,
  update: Partial<TaskExecutionView>,
): ExecutionBoardView {
  return {
    ...board,
    tasks: board.tasks.map((task) =>
      task.task_id === taskId ? { ...task, ...update } : task,
    ),
  };
}

async function mockExecution(page: Page) {
  let board: ExecutionBoardView = structuredClone(executionBoardFixture);
  let sequence = 10;
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1", "");
    const method = request.method();
    if (path === "/auth/session" && method === "GET") return json(route, sessionFixture);
    if (path === `/projects/${ids.project}` && method === "GET") {
      return json(route, projectFixture);
    }
    if (path === `/projects/${ids.project}/execution` && method === "GET") {
      return json(route, board);
    }
    const statusMatch = path.match(/^\/tasks\/([^/]+)\/status$/);
    if (statusMatch && method === "POST") {
      expect(request.headers()["if-match"]).toBeTruthy();
      expect(request.headers()["idempotency-key"]).toBeTruthy();
      const taskId = statusMatch[1];
      const payload = request.postDataJSON() as {
        to_status: TaskStatus;
        reason?: string;
      };
      const current = board.tasks.find((task) => task.task_id === taskId);
      if (!current) return json(route, { detail: "Task not found" }, 404);
      const fromStatus = current.status;
      let updated: TaskExecutionView = {
        ...current,
        status: payload.to_status,
        blocked_reason:
          payload.to_status === "blocked" ? payload.reason ?? null : null,
        row_version: current.row_version + 1,
        status_changed_at: `2026-08-03T08:${sequence}:00Z`,
      };
      if (payload.to_status === "completed") {
        updated = { ...updated, progress_fraction: "1" };
      }
      const primary = event(
        updated,
        fromStatus,
        payload.to_status,
        payload.reason ??
          (payload.to_status === "completed"
            ? "Owner completed the task."
            : "Owner started task execution."),
        sequence++,
      );
      board = withTask(board, taskId, updated);
      const readinessChanges: TaskStatusEventView[] = [];
      if (taskId === ids.task1 && payload.to_status === "completed") {
        const successor = board.tasks.find((task) => task.task_id === ids.task2);
        if (successor) {
          const ready = {
            ...successor,
            status: "ready" as const,
            prerequisites_satisfied: true,
            ready_to_start: true,
            incomplete_predecessor_refs: [],
            row_version: successor.row_version + 1,
          };
          const readyEvent = event(
            ready,
            "pending",
            "ready",
            "Readiness recalculated from active finish-to-start dependencies.",
            sequence++,
          );
          readyEvent.actor_id = null;
          readyEvent.actor_type = "system";
          readinessChanges.push(readyEvent);
          board = withTask(board, ids.task2, ready);
          board = {
            ...board,
            progress: {
              ...board.progress,
              state_hash: `sha256:${"3".repeat(64)}`,
              project: {
                ...board.progress.project,
                fraction: "0.6",
                weighted_completed_hours: "12",
              },
              tasks: board.progress.tasks.map((task) =>
                task.task_id === ids.task1
                  ? { ...task, fraction: "1", status: "completed" }
                  : task.task_id === ids.task2
                    ? { ...task, status: "ready" }
                    : task,
              ),
            },
          };
        }
      }
      if (taskId === ids.task2 && payload.to_status === "blocked") {
        board = {
          ...board,
          health: {
            ...board.health,
            state_hash: `sha256:${"4".repeat(64)}`,
            label: "At risk",
            rule_codes: ["BLOCKED_CRITICAL_TASK"],
            evidence: [
              {
                rule_code: "BLOCKED_CRITICAL_TASK",
                values: { blocked_count: "1" },
                references: ["TASK-002"],
              },
            ],
            detections: [
              {
                code: "BLOCKED_TASKS",
                severity: "warning",
                references: ["TASK-002"],
                values: { blocked_count: "1" },
                calculation_version: "monitoring-v1",
              },
            ],
          },
        };
      }
      board = {
        ...board,
        recent_events: [
          primary,
          ...readinessChanges,
          ...board.recent_events,
        ],
      };
      return json(route, {
        task: board.tasks.find((task) => task.task_id === taskId),
        event: primary,
        readiness_changes: readinessChanges,
        progress: board.progress,
        health: board.health,
      });
    }
    return json(
      route,
      {
        type: "about:blank",
        title: "Unhandled mocked request",
        status: 404,
        code: "unhandled",
        detail: `${method} ${path}`,
        request_id: "playwright-execution",
        errors: [],
      },
      404,
    );
  });
}

async function expectNoHorizontalOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    content: document.documentElement.scrollWidth,
    offenders: [...document.querySelectorAll<HTMLElement>("body *")]
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          selector: `${element.tagName.toLowerCase()}.${element.className}`,
          left: Math.round(rect.left),
          right: Math.round(rect.right),
          width: Math.round(rect.width),
        };
      })
      .filter((item) => item.left < -1 || item.right > window.innerWidth + 1)
      .slice(0, 12),
  }));
  expect(
    dimensions.content,
    `overflowing elements: ${JSON.stringify(dimensions.offenders)}`,
  ).toBeLessThanOrEqual(dimensions.viewport);
}

function taskCard(page: Page, heading: string) {
  return page.getByRole("heading", { name: heading }).locator("..");
}

test("owner executes ready work, propagates readiness, and records a critical blocker", async ({
  page,
}) => {
  await mockExecution(page);
  await page.goto(`/projects/${ids.project}/overview`);
  await expect(
    page.getByRole("heading", { name: `${projectFixture.name} overview` }),
  ).toBeVisible();
  await expect(page.getByText("TASK-001 · Build request form")).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.getByRole("link", { name: "Board", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: `${projectFixture.name} execution board`,
    }),
  ).toBeVisible();
  await expectNoHorizontalOverflow(page);

  const first = taskCard(page, "Build request form");
  await first.getByRole("button", { name: "Start task" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Confirm change" }).click();
  await expect(first.getByText("in progress", { exact: true })).toBeVisible();
  await first.getByRole("button", { name: "Complete task" }).click();
  await page.getByRole("button", { name: "Confirm change" }).click();
  await expect(first.getByText("completed", { exact: true })).toBeVisible();
  await expect(page.getByText("60%")).toBeVisible();

  const successor = taskCard(page, "Render request status");
  await expect(successor.getByText("ready", { exact: true })).toBeVisible();
  await successor.getByRole("button", { name: "Start task" }).click();
  await page.getByRole("button", { name: "Confirm change" }).click();
  await successor.getByRole("button", { name: "Block" }).click();
  await page.getByLabel("Reason *").fill(
    "The external approval contract is unavailable.",
  );
  await page.getByRole("button", { name: "Confirm blocker" }).click();

  await expect(page.getByText("At risk")).toBeVisible();
  await expect(page.getByText("BLOCKED_CRITICAL_TASK")).toBeVisible();
  await expect(
    successor.getByText("The external approval contract is unavailable."),
  ).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.reload();
  await expect(
    page.getByText("The external approval contract is unavailable.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Health", exact: true }).click();
  await expect(page.getByRole("heading", { name: "At risk" })).toBeVisible();
  await expect(page.getByText("BLOCKED_TASKS")).toBeVisible();
  await expect(page.getByRole("link", { name: "TASK-002" }).first()).toBeVisible();
  await expectNoHorizontalOverflow(page);
});
