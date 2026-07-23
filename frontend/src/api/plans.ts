import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { requestJson } from "./client";
import type {
  DependencyCreatePayload,
  DependencyView,
  MilestoneCreatePayload,
  MilestoneView,
  PlanDiffView,
  PlanGraphView,
  PlanValidationView,
  PlanVersionSummary,
  TaskCreatePayload,
  TaskView,
} from "./types";

export const planKeys = {
  all: ["plans"] as const,
  project: (projectId: string) => [...planKeys.all, "project", projectId] as const,
  detail: (versionId: string) => [...planKeys.all, "detail", versionId] as const,
};

function versionHeaders(rowVersion: number): HeadersInit {
  return { "If-Match": String(rowVersion) };
}

export function listPlanVersions(projectId: string): Promise<PlanVersionSummary[]> {
  return requestJson<PlanVersionSummary[]>(`/projects/${projectId}/plan-versions`);
}

export function getPlanVersion(versionId: string): Promise<PlanGraphView> {
  return requestJson<PlanGraphView>(`/plan-versions/${versionId}`);
}

export function updatePlanVersion(
  versionId: string,
  rowVersion: number,
  payload: {
    reason?: string;
    analysis_summary?: string;
    mvp_boundary?: string[];
    excluded_scope?: string[];
    assumptions?: Array<Record<string, unknown>>;
  },
): Promise<PlanGraphView> {
  return requestJson<PlanGraphView>(`/plan-versions/${versionId}`, {
    method: "PATCH",
    headers: versionHeaders(rowVersion),
    body: JSON.stringify(payload),
  });
}

export function validatePlanVersion(
  versionId: string,
  rowVersion: number,
): Promise<PlanValidationView> {
  return requestJson<PlanValidationView>(`/plan-versions/${versionId}/validate`, {
    method: "POST",
    headers: versionHeaders(rowVersion),
  });
}

export function submitPlanReview(
  versionId: string,
  rowVersion: number,
): Promise<PlanGraphView> {
  return requestJson<PlanGraphView>(`/plan-versions/${versionId}/submit-review`, {
    method: "POST",
    headers: versionHeaders(rowVersion),
  });
}

export function requestPlanChanges(
  versionId: string,
  rowVersion: number,
  reason: string,
): Promise<PlanGraphView> {
  return requestJson<PlanGraphView>(`/plan-versions/${versionId}/request-changes`, {
    method: "POST",
    headers: versionHeaders(rowVersion),
    body: JSON.stringify({ reason }),
  });
}

export function approvePlanVersion(
  versionId: string,
  rowVersion: number,
  contentHash: string,
  reason?: string,
): Promise<PlanGraphView> {
  return requestJson<PlanGraphView>(`/plan-versions/${versionId}/approve`, {
    method: "POST",
    headers: versionHeaders(rowVersion),
    body: JSON.stringify({ content_hash: contentHash, reason }),
  });
}

export function archivePlanVersion(
  versionId: string,
  rowVersion: number,
): Promise<PlanGraphView> {
  return requestJson<PlanGraphView>(`/plan-versions/${versionId}/archive`, {
    method: "POST",
    headers: versionHeaders(rowVersion),
  });
}

export function comparePlanVersions(
  fromVersionId: string,
  toVersionId: string,
): Promise<PlanDiffView> {
  return requestJson<PlanDiffView>(
    `/plan-versions/${fromVersionId}/compare/${toVersionId}`,
  );
}

export function listMilestones(versionId: string): Promise<MilestoneView[]> {
  return requestJson<MilestoneView[]>(`/plan-versions/${versionId}/milestones`);
}

export function createMilestone(
  versionId: string,
  rowVersion: number,
  payload: MilestoneCreatePayload,
): Promise<{ item: MilestoneView; plan: PlanVersionSummary }> {
  return requestJson(`/plan-versions/${versionId}/milestones`, {
    method: "POST",
    headers: versionHeaders(rowVersion),
    body: JSON.stringify(payload),
  });
}

export function updateMilestone(
  versionId: string,
  milestoneId: string,
  rowVersion: number,
  payload: Partial<MilestoneCreatePayload>,
): Promise<{ item: MilestoneView; plan: PlanVersionSummary }> {
  return requestJson(`/plan-versions/${versionId}/milestones/${milestoneId}`, {
    method: "PATCH",
    headers: versionHeaders(rowVersion),
    body: JSON.stringify(payload),
  });
}

export function deleteMilestone(
  versionId: string,
  milestoneId: string,
  rowVersion: number,
): Promise<PlanVersionSummary> {
  return requestJson<PlanVersionSummary>(
    `/plan-versions/${versionId}/milestones/${milestoneId}`,
    {
      method: "DELETE",
      headers: versionHeaders(rowVersion),
    },
  );
}

export function listTasks(versionId: string): Promise<TaskView[]> {
  return requestJson<TaskView[]>(`/plan-versions/${versionId}/tasks`);
}

export function createTask(
  versionId: string,
  rowVersion: number,
  payload: TaskCreatePayload,
): Promise<{ item: TaskView; plan: PlanVersionSummary }> {
  return requestJson(`/plan-versions/${versionId}/tasks`, {
    method: "POST",
    headers: versionHeaders(rowVersion),
    body: JSON.stringify(payload),
  });
}

export function updateTask(
  versionId: string,
  taskId: string,
  rowVersion: number,
  payload: Partial<TaskCreatePayload>,
): Promise<{ item: TaskView; plan: PlanVersionSummary }> {
  return requestJson(`/plan-versions/${versionId}/tasks/${taskId}`, {
    method: "PATCH",
    headers: versionHeaders(rowVersion),
    body: JSON.stringify(payload),
  });
}

export function deleteTask(
  versionId: string,
  taskId: string,
  rowVersion: number,
): Promise<PlanVersionSummary> {
  return requestJson<PlanVersionSummary>(
    `/plan-versions/${versionId}/tasks/${taskId}`,
    {
      method: "DELETE",
      headers: versionHeaders(rowVersion),
    },
  );
}

export function listDependencies(versionId: string): Promise<DependencyView[]> {
  return requestJson<DependencyView[]>(`/plan-versions/${versionId}/dependencies`);
}

export function createDependency(
  versionId: string,
  rowVersion: number,
  payload: DependencyCreatePayload,
): Promise<{ item: DependencyView; plan: PlanVersionSummary }> {
  return requestJson(`/plan-versions/${versionId}/dependencies`, {
    method: "POST",
    headers: versionHeaders(rowVersion),
    body: JSON.stringify(payload),
  });
}

export function deleteDependency(
  versionId: string,
  dependencyId: string,
  rowVersion: number,
): Promise<PlanVersionSummary> {
  return requestJson<PlanVersionSummary>(
    `/plan-versions/${versionId}/dependencies/${dependencyId}`,
    {
      method: "DELETE",
      headers: versionHeaders(rowVersion),
    },
  );
}

export function usePlanVersions(projectId: string) {
  return useQuery({
    queryKey: planKeys.project(projectId),
    queryFn: () => listPlanVersions(projectId),
  });
}

export function usePlanVersion(versionId: string) {
  return useQuery({
    queryKey: planKeys.detail(versionId),
    queryFn: () => getPlanVersion(versionId),
  });
}

export function usePlanLifecycleMutation(versionId: string) {
  const queryClient = useQueryClient();
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: planKeys.detail(versionId) });
  };
  return {
    validate: useMutation({
      mutationFn: (rowVersion: number) => validatePlanVersion(versionId, rowVersion),
      onSuccess: refresh,
    }),
    submitReview: useMutation({
      mutationFn: (rowVersion: number) => submitPlanReview(versionId, rowVersion),
      onSuccess: refresh,
    }),
    requestChanges: useMutation({
      mutationFn: ({ rowVersion, reason }: { rowVersion: number; reason: string }) =>
        requestPlanChanges(versionId, rowVersion, reason),
      onSuccess: refresh,
    }),
    approve: useMutation({
      mutationFn: ({
        rowVersion,
        contentHash,
        reason,
      }: {
        rowVersion: number;
        contentHash: string;
        reason?: string;
      }) => approvePlanVersion(versionId, rowVersion, contentHash, reason),
      onSuccess: refresh,
    }),
    archive: useMutation({
      mutationFn: (rowVersion: number) => archivePlanVersion(versionId, rowVersion),
      onSuccess: refresh,
    }),
  };
}
