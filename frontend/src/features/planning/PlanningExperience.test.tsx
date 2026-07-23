import { HttpResponse, http } from "msw";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "../../app/App";
import { routes } from "../../app/router";
import {
  clarificationFixture,
  ids,
  projectFixture,
  runFixture,
  runStepsFixture,
  sessionFixture,
} from "../../test/fixtures";
import { server } from "../../test/server";

function renderRoute(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<App router={router} />);
}

describe("planning and clarification experience", () => {
  it("shows concise accessible run progress without raw model details", async () => {
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () => HttpResponse.json(runFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}/steps`, () =>
        HttpResponse.json(runStepsFixture),
      ),
    );
    const view = renderRoute(`/projects/${ids.project}/planning?run=${ids.run}`);

    expect(await screen.findByRole("heading", { name: projectFixture.name })).toBeInTheDocument();
    expect(screen.getByText("Check project intake")).toBeInTheDocument();
    expect(screen.getAllByText("Resolve clarifications")).toHaveLength(2);
    expect(screen.queryByText("Internal purpose not rendered")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Answer questions" })).toHaveAttribute(
      "href",
      `/projects/${ids.project}/clarify?run=${ids.run}`,
    );
    const results = await axe.run(view.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it("supports keyboard assumption acceptance and submits typed answers", async () => {
    let submitted: unknown;
    server.use(
      http.get("*/api/v1/auth/session", () => HttpResponse.json(sessionFixture)),
      http.get(`*/api/v1/projects/${ids.project}`, () => HttpResponse.json(projectFixture)),
      http.get(`*/api/v1/agent-runs/${ids.run}`, () => HttpResponse.json(runFixture)),
      http.get(`*/api/v1/projects/${ids.project}/clarifications`, () =>
        HttpResponse.json([clarificationFixture]),
      ),
      http.post(`*/api/v1/projects/${ids.project}/clarifications`, async ({ request }) => {
        submitted = await request.json();
        return HttpResponse.json({
          run: runFixture,
          questions: [{ ...clarificationFixture, status: "answered", answer_json: "Facilities" }],
          resumed: false,
        });
      }),
    );
    const user = userEvent.setup();
    const view = renderRoute(`/projects/${ids.project}/clarify?run=${ids.run}`);

    expect(await screen.findByRole("heading", { name: `Clarify ${projectFixture.name}` })).toBeInTheDocument();
    const assumption = screen.getByRole("button", { name: "Use assumption" });
    assumption.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("radio", { name: "Facilities" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Save answers and resume" }));
    await waitFor(() =>
      expect(submitted).toEqual({
        run_id: ids.run,
        answers: [{ question_id: ids.question, answer: "Facilities" }],
      }),
    );
    expect(screen.getByText("Draft answers saved in this browser")).toBeInTheDocument();
    const results = await axe.run(view.container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });
});
