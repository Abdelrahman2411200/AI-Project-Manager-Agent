import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listProjects } from "../api/projects";

export function ProjectsPage() {
  const projects = useQuery({ queryKey: ["projects"], queryFn: listProjects });

  if (projects.isPending) {
    return <section className="content-state" aria-live="polite"><span className="loading-spinner" aria-hidden="true" /><h1>Loading your projects…</h1></section>;
  }
  if (projects.isError) {
    return <section className="content-state" role="alert"><span className="eyebrow">Unable to load</span><h1>Your projects are temporarily unavailable.</h1><button className="button secondary" type="button" onClick={() => void projects.refetch()}>Try again</button></section>;
  }

  return (
    <div className="page-stack">
      <header className="page-header">
        <div><span className="eyebrow">Owned workspace</span><h1>Projects</h1><p>Shape each project’s intent before the planning workflow begins.</p></div>
        <Link className="button primary" to="/projects/new">Create project</Link>
      </header>
      {projects.data.items.length === 0 ? (
        <section className="empty-projects">
          <span className="empty-projects-icon" aria-hidden="true">+</span>
          <h2>Create your first project</h2>
          <p>Capture the goal, delivery window, capacity, requirements, and constraints.</p>
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
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
