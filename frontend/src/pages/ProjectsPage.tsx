import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { archiveProject, listProjects, projectKeys } from "../api/projects";
import type { ProjectView } from "../api/types";
import { errorMessage } from "../api/errorUtils";
import { FeedbackBanner } from "../components/Feedback";

export function ProjectsPage() {
  const queryClient = useQueryClient();
  const [pendingArchive, setPendingArchive] = useState<string | null>(null);
  const projects = useQuery({
    queryKey: projectKeys.list(),
    queryFn: listProjects,
    retry: false,
  });
  const archive = useMutation({
    mutationFn: (project: ProjectView) => archiveProject(project.id, project.row_version),
    onSuccess: async () => {
      setPendingArchive(null);
      await queryClient.invalidateQueries({ queryKey: projectKeys.all });
    },
  });

  if (projects.isPending) {
    return (
      <div className="page-stack" aria-busy="true" aria-live="polite">
        <header className="page-header"><div><span className="eyebrow">Owned workspace</span><h1>Projects</h1></div></header>
        <span className="sr-only">Loading your projects…</span>
        <section className="project-grid" aria-hidden="true">
          {[1, 2, 3].map((item) => <article className="project-card skeleton-card" key={item}><span /><span /><span /></article>)}
        </section>
      </div>
    );
  }
  if (projects.isError) {
    return <section className="content-state" role="alert"><span className="eyebrow">Unable to load</span><h1>Your projects are temporarily unavailable.</h1><p>{errorMessage(projects.error, "Try loading the project list again.")}</p><button className="button secondary" type="button" onClick={() => void projects.refetch()}>Try again</button></section>;
  }

  return (
    <div className="page-stack">
      <header className="page-header">
        <div><span className="eyebrow">Owned workspace</span><h1>Projects</h1><p>Shape each project’s intent, guide its planning workflow, and approve the exact delivery plan.</p></div>
        <Link className="button primary" to="/projects/new">Create project</Link>
      </header>
      {archive.isError ? <FeedbackBanner tone="danger" title="Project was not archived">{errorMessage(archive.error, "Refresh the project and try again.")}</FeedbackBanner> : null}
      {projects.data.items.length === 0 ? (
        <section className="empty-projects">
          <span className="empty-projects-icon" aria-hidden="true">+</span>
          <h2>Create your first project</h2>
          <p>Capture the goal, delivery window, capacity, requirements, exclusions, and constraints.</p>
          <Link className="button primary" to="/projects/new">Start project intake</Link>
        </section>
      ) : (
        <section className="project-grid" aria-label="Your projects">
          {projects.data.items.map((project) => (
            <article className="project-card" key={project.id}>
              <div className="project-card-topline"><span className={`project-status ${project.status}`}>{project.status}</span><span>v{project.row_version}</span></div>
              <h2><Link to={`/projects/${project.id}`}>{project.name}</Link></h2>
              <p>{project.goal}</p>
              <dl><div><dt>Deadline</dt><dd>{project.deadline ?? "Not set"}</dd></div><div><dt>Capacity</dt><dd>{Number(project.capacity_hours_per_week)} h/week</dd></div></dl>
              {project.status === "active" ? (
                pendingArchive === project.id ? (
                  <div className="inline-confirm" role="alert">
                    <span>Archive this project?</span>
                    <button className="button compact secondary" type="button" onClick={() => setPendingArchive(null)}>Keep</button>
                    <button className="button compact danger" type="button" disabled={archive.isPending} onClick={() => archive.mutate(project)}>Archive</button>
                  </div>
                ) : (
                  <button className="text-button danger-text project-archive" type="button" onClick={() => setPendingArchive(project.id)}>Archive project</button>
                )
              ) : null}
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
