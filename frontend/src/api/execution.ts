import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { requestJson } from "./client";
import { isPermissionError } from "./errorUtils";
import type {
  ExecutionBoardView,
  ProjectHealthView,
  ProjectProgressView,
  TaskProgressMutationView,
  TaskStatus,
  TaskStatusEventView,
  TaskStatusMutationView,
} from "./types";

export const executionKeys = {
  all: ["execution"] as const,
  board: (projectId: string) => [...executionKeys.all, "board", projectId] as const,
  progress: (projectId: string) =>
    [...executionKeys.all, "progress", projectId] as const,
  health: (projectId: string) =>
    [...executionKeys.all, "health", projectId] as const,
  events: (taskId: string) => [...executionKeys.all, "events", taskId] as const,
};

function mutationHeaders(rowVersion: number, idempotencyKey: string): HeadersInit {
  return {
    "If-Match": String(rowVersion),
    "Idempotency-Key": idempotencyKey,
  };
}

function createIdempotencyKey(action: string, taskId: string): string {
  return `${action}-${taskId}-${crypto.randomUUID()}`;
}

export function getExecutionBoard(projectId: string): Promise<ExecutionBoardView> {
  return requestJson<ExecutionBoardView>(`/projects/${projectId}/execution`);
}

export function getProjectProgress(projectId: string): Promise<ProjectProgressView> {
  return requestJson<ProjectProgressView>(`/projects/${projectId}/progress`);
}

export function getProjectHealth(projectId: string): Promise<ProjectHealthView> {
  return requestJson<ProjectHealthView>(`/projects/${projectId}/health`);
}

export function listTaskEvents(taskId: string): Promise<TaskStatusEventView[]> {
  return requestJson<TaskStatusEventView[]>(`/tasks/${taskId}/events`);
}

export function updateTaskStatus(
  taskId: string,
  rowVersion: number,
  toStatus: TaskStatus,
  reason?: string,
): Promise<TaskStatusMutationView> {
  return requestJson<TaskStatusMutationView>(`/tasks/${taskId}/status`, {
    method: "POST",
    headers: mutationHeaders(
      rowVersion,
      createIdempotencyKey(`status-${toStatus}`, taskId),
    ),
    body: JSON.stringify({ to_status: toStatus, reason }),
  });
}

export function updateTaskProgress(
  taskId: string,
  rowVersion: number,
  fraction: number,
  actualEffortHours: number,
  note?: string,
): Promise<TaskProgressMutationView> {
  return requestJson<TaskProgressMutationView>(`/tasks/${taskId}/progress`, {
    method: "POST",
    headers: mutationHeaders(
      rowVersion,
      createIdempotencyKey("progress", taskId),
    ),
    body: JSON.stringify({
      fraction,
      actual_effort_hours: actualEffortHours,
      note,
    }),
  });
}

export function useExecutionBoard(projectId: string) {
  return useQuery({
    queryKey: executionKeys.board(projectId),
    queryFn: () => getExecutionBoard(projectId),
    enabled: Boolean(projectId),
    retry: (failureCount, error) =>
      !isPermissionError(error) && failureCount < 2,
  });
}

export function useExecutionMutations(projectId: string) {
  const queryClient = useQueryClient();
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: executionKeys.board(projectId) }),
      queryClient.invalidateQueries({ queryKey: executionKeys.progress(projectId) }),
      queryClient.invalidateQueries({ queryKey: executionKeys.health(projectId) }),
    ]);
  };
  return {
    status: useMutation({
      mutationFn: ({
        taskId,
        rowVersion,
        toStatus,
        reason,
      }: {
        taskId: string;
        rowVersion: number;
        toStatus: TaskStatus;
        reason?: string;
      }) => updateTaskStatus(taskId, rowVersion, toStatus, reason),
      onSuccess: (result) => {
        queryClient.setQueryData<ExecutionBoardView>(
          executionKeys.board(projectId),
          (current) => {
            if (!current) return current;
            const changed = new Map([
              [result.task.task_id, result.task],
            ]);
            for (const event of result.readiness_changes) {
              const existing = current.tasks.find(
                (task) => task.task_id === event.task_id,
              );
              if (existing) {
                changed.set(event.task_id, {
                  ...existing,
                  status: event.to_status,
                  status_changed_at: event.occurred_at,
                  row_version: existing.row_version + 1,
                  prerequisites_satisfied: event.to_status === "ready",
                  ready_to_start: event.to_status === "ready",
                  incomplete_predecessor_refs:
                    event.to_status === "ready"
                      ? []
                      : existing.incomplete_predecessor_refs,
                });
              }
            }
            return {
              ...current,
              tasks: current.tasks.map(
                (task) => changed.get(task.task_id) ?? task,
              ),
              recent_events: [
                result.event,
                ...result.readiness_changes,
                ...current.recent_events,
              ].slice(0, 30),
              progress: result.progress,
              health: result.health,
            };
          },
        );
        void refresh();
      },
    }),
    progress: useMutation({
      mutationFn: ({
        taskId,
        rowVersion,
        fraction,
        actualEffortHours,
        note,
      }: {
        taskId: string;
        rowVersion: number;
        fraction: number;
        actualEffortHours: number;
        note?: string;
      }) =>
        updateTaskProgress(
          taskId,
          rowVersion,
          fraction,
          actualEffortHours,
          note,
        ),
      onSuccess: (result) => {
        queryClient.setQueryData<ExecutionBoardView>(
          executionKeys.board(projectId),
          (current) =>
            current
              ? {
                  ...current,
                  tasks: current.tasks.map((task) =>
                    task.task_id === result.task.task_id ? result.task : task,
                  ),
                  progress: result.progress,
                  health: result.health,
                }
              : current,
        );
        void refresh();
      },
    }),
  };
}
