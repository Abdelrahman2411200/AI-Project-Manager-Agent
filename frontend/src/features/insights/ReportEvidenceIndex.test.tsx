import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { EvidenceFact } from "../../api/types";
import { ReportEvidenceIndex } from "./ReportEvidenceIndex";

const evidence: Record<string, EvidenceFact> = {
  "TASK-010": {
    entity_type: "task",
    entity_ref: "TASK-010",
    fact_key: "task_snapshot",
    value: {
      title: "Publish the release",
      status: "ready",
      priority: "Must",
      progress: "0%",
      planned_start: "2026-08-09",
      planned_finish: "2026-08-10",
    },
  },
  "TASK-002": {
    entity_type: "task",
    entity_ref: "TASK-002",
    fact_key: "blocker",
    value: {
      title: "Confirm university access",
      status: "blocked",
      reason: "Approval is pending",
    },
  },
  "FORECAST-CURRENT": {
    entity_type: "forecast",
    entity_ref: "FORECAST-CURRENT",
    fact_key: "remaining_work_schedule",
    value: {
      deadline_feasible: true,
      project_finish: "2026-08-10",
      warnings: [],
      tasks: {
        "opaque-database-id": {
          stable_key: "TASK-002",
          start_date: "2026-08-03",
          finish_date: "2026-08-04",
        },
      },
    },
  },
  "EVENT-4a8857d7-12ab-4cde-8fab-1234567890ab": {
    entity_type: "event",
    entity_ref: "EVENT-4a8857d7-12ab-4cde-8fab-1234567890ab",
    fact_key: "task_status_changed",
    value: {
      task_ref: "TASK-002",
      from_status: "IN_PROGRESS",
      to_status: "COMPLETED",
      occurred_at: "2026-08-04T14:00:00Z",
    },
  },
};

describe("ReportEvidenceIndex", () => {
  it("separates tasks from claim evidence and renders nested facts as labelled fields", () => {
    const { container } = render(<ReportEvidenceIndex evidence={evidence} />);

    const taskSection = screen.getByRole("heading", { name: "Task index" }).closest("section");
    expect(taskSection).not.toBeNull();
    const taskItems = within(taskSection as HTMLElement).getAllByRole("listitem");
    expect(taskItems).toHaveLength(2);
    expect(taskItems[0]).toHaveTextContent("TASK-002");
    expect(taskItems[0]).toHaveTextContent("Confirm university access");
    expect(taskItems[0]).toHaveTextContent("Blocked");
    expect(taskItems[1]).toHaveTextContent("TASK-010");

    const evidenceSection = screen.getByRole("heading", { name: "Evidence index" }).closest("section");
    expect(evidenceSection).not.toBeNull();
    expect(within(evidenceSection as HTMLElement).getByText("Remaining work schedule")).toBeVisible();
    expect(within(evidenceSection as HTMLElement).getByText("Deadline feasible")).toBeVisible();
    expect(within(evidenceSection as HTMLElement).getByText("Yes")).toBeVisible();
    expect(within(evidenceSection as HTMLElement).getByText("None recorded")).toBeVisible();
    expect(within(evidenceSection as HTMLElement).getByRole("heading", { name: "TASK-002" })).toBeVisible();
    expect(within(evidenceSection as HTMLElement).getByText("Event 4A8857D7")).toBeVisible();
    expect(within(evidenceSection as HTMLElement).getByText("Task status changed")).toBeVisible();
    expect(container.textContent).not.toContain('{"');
    expect(container.textContent).not.toContain("opaque-database-id");
    expect(container.textContent).not.toContain("4a8857d7-12ab-4cde-8fab-1234567890ab");
  });
});
