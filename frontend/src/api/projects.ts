import { requestJson } from "./client";
import type { ProjectCreatePayload, ProjectList, ProjectView } from "./types";

export const projectKeys = {
  all: ["projects"] as const,
  list: () => [...projectKeys.all, "list"] as const,
  detail: (projectId: string) => [...projectKeys.all, "detail", projectId] as const,
};

export function listProjects(): Promise<ProjectList> {
  return requestJson<ProjectList>("/projects");
}

export function createProject(payload: ProjectCreatePayload): Promise<ProjectView> {
  return requestJson<ProjectView>("/projects", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getProject(projectId: string): Promise<ProjectView> {
  return requestJson<ProjectView>(`/projects/${projectId}`);
}

export function archiveProject(projectId: string, rowVersion: number): Promise<ProjectView> {
  return requestJson<ProjectView>(`/projects/${projectId}`, {
    method: "DELETE",
    headers: { "If-Match": String(rowVersion) },
  });
}
