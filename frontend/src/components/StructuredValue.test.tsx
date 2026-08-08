import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StructuredValue } from "./StructuredValue";
import { cleanNarrativeText } from "../utils/display";

describe("StructuredValue", () => {
  it("presents nested API values without serialized JSON or opaque collection keys", () => {
    const { container } = render(
      <StructuredValue
        value={{
          status: "IN_PROGRESS",
          occurred_at: "2026-07-26T14:00:00Z",
          deadline_feasible: true,
          rule_codes: ["READY_WORK_AVAILABLE", "BLOCKED_TASKS"],
          tasks: {
            "7f987909-opaque-database-key": {
              stable_key: "TASK-004",
              title: "Verify the release",
              warnings: [],
            },
          },
        }}
      />,
    );

    expect(screen.getByText("Status")).toBeVisible();
    expect(screen.getByText("In progress")).toBeVisible();
    expect(screen.getByText("Jul 26, 2026, 2:00 PM UTC")).toBeVisible();
    expect(screen.getByText("Yes")).toBeVisible();
    expect(screen.getByText("Ready work available")).toBeVisible();
    expect(screen.getByRole("heading", { name: "TASK-004" })).toBeVisible();
    expect(screen.getByText("None recorded")).toBeVisible();
    expect(container.textContent).not.toContain("opaque-database-key");
    expect(container.textContent).not.toContain("[object Object]");
    expect(container.textContent).not.toContain('{"');
  });

  it("removes internal prompt-boundary markers from displayed report prose", () => {
    expect(cleanNarrativeText("<UNTRUSTED_PROJECT_DATA>\nDelivery is on track.\n</UNTRUSTED_PROJECT_DATA>"))
      .toBe("Delivery is on track.");
  });
});
