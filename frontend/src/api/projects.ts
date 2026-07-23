import { requestJson } from "./client";
import type { ProjectCreatePayload, ProjectList, ProjectView } from "./types";

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
