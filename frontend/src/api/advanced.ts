import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { requestJson } from "./client";
import { planKeys } from "./plans";
import type {
  PlanComparisonView,
  RegenerationProposalView,
  ScenarioOverrides,
  ScenarioView,
} from "./types";

export const advancedKeys = {
  all: ["advanced-intelligence"] as const,
  scenario: (scenarioId: string) =>
    [...advancedKeys.all, "scenario", scenarioId] as const,
  comparison: (fromId: string, toId: string) =>
    [...advancedKeys.all, "comparison", fromId, toId] as const,
};

export function createScenario(
  projectId: string,
  payload: {
    name: string;
    baseline_version_id?: string;
    overrides: ScenarioOverrides;
  },
): Promise<ScenarioView> {
  return requestJson(`/projects/${projectId}/scenarios`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(payload),
  });
}

export function getScenario(scenarioId: string): Promise<ScenarioView> {
  return requestJson(`/scenarios/${scenarioId}`);
}

export function comparePlanImpact(
  fromId: string,
  toId: string,
): Promise<PlanComparisonView> {
  return requestJson(`/plan-versions/${fromId}/compare/${toId}/impact`);
}

export function createRegeneration(
  versionId: string,
  payload: {
    targets: Array<{
      entity_type: "task" | "milestone";
      stable_key: string;
      fields: string[];
    }>;
    replacements: Array<{
      entity_type: "task" | "milestone";
      stable_key: string;
      values: Record<string, unknown>;
    }>;
  },
): Promise<RegenerationProposalView> {
  return requestJson(`/plan-versions/${versionId}/regenerations`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(payload),
  });
}

export function decideRegeneration(
  proposal: RegenerationProposalView,
  decision: "approve" | "reject",
): Promise<RegenerationProposalView> {
  return requestJson(`/regeneration-proposals/${proposal.id}/${decision}`, {
    method: "POST",
    headers: { "If-Match": String(proposal.row_version) },
    body: JSON.stringify({ reason: "Owner reviewed the deterministic proposal diff." }),
  });
}

export function useScenario(scenarioId: string) {
  return useQuery({
    queryKey: advancedKeys.scenario(scenarioId),
    queryFn: () => getScenario(scenarioId),
    enabled: Boolean(scenarioId) && scenarioId !== "new",
  });
}

export function useRegenerationDecision(versionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      proposal,
      decision,
    }: {
      proposal: RegenerationProposalView;
      decision: "approve" | "reject";
    }) => decideRegeneration(proposal, decision),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: planKeys.detail(versionId) });
    },
  });
}
