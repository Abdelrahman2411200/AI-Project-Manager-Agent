import { requestJson } from "./client";
import type {
  AgentRunStepView,
  AgentRunView,
  ClarificationResumeView,
  ClarificationView,
} from "./types";

const nonPollingStatuses = new Set([
  "waiting_for_user",
  "partial",
  "failed",
  "completed",
  "cancelled",
]);

export const runKeys = {
  all: ["planning-runs"] as const,
  detail: (runId: string) => [...runKeys.all, "detail", runId] as const,
  steps: (runId: string) => [...runKeys.all, "steps", runId] as const,
  clarifications: (projectId: string, runId: string) =>
    [...runKeys.all, "clarifications", projectId, runId] as const,
};

export function startPlanningRun(
  projectId: string,
  tokenBudget = 50_000,
  idempotencyKey = crypto.randomUUID(),
): Promise<AgentRunView> {
  return requestJson<AgentRunView>(`/projects/${projectId}/planning-runs`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ token_budget: tokenBudget }),
  });
}

export function getAgentRun(runId: string): Promise<AgentRunView> {
  return requestJson<AgentRunView>(`/agent-runs/${runId}`);
}

export function listAgentRunSteps(runId: string): Promise<AgentRunStepView[]> {
  return requestJson<AgentRunStepView[]>(`/agent-runs/${runId}/steps`);
}

export function cancelAgentRun(runId: string): Promise<AgentRunView> {
  return requestJson<AgentRunView>(`/agent-runs/${runId}/cancel`, { method: "POST" });
}

export function listClarifications(
  projectId: string,
  runId?: string,
): Promise<ClarificationView[]> {
  const query = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return requestJson<ClarificationView[]>(`/projects/${projectId}/clarifications${query}`);
}

export function answerClarifications(
  projectId: string,
  runId: string,
  answers: Array<{ question_id: string; answer: unknown }>,
): Promise<ClarificationResumeView> {
  return requestJson<ClarificationResumeView>(`/projects/${projectId}/clarifications`, {
    method: "POST",
    body: JSON.stringify({ run_id: runId, answers }),
  });
}

export function planningRunPollInterval(run: AgentRunView | undefined): number | false {
  return run && nonPollingStatuses.has(run.status) ? false : 1_000;
}
