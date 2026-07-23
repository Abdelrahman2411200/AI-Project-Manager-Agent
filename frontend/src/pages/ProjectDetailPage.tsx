import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getProject } from "../api/projects";

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const project = useQuery({
    queryKey: ["projects", projectId],
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId),
  });

  if (project.isPending) {
    return <section className="content-state" aria-live="polite"><span className="loading-spinner" aria-hidden="true" /><h1>Loading project…</h1></section>;
  }
  if (project.isError) {
    return <section className="content-state" role="alert"><h1>Project unavailable</h1><Link to="/projects">Return to projects</Link></section>;
  }

  return (
    <div className="page-stack">
      <header className="page-header">
        <div><span className="eyebrow">Project intake · version {project.data.row_version}</span><h1>{project.data.name}</h1><p>{project.data.goal}</p></div>
        <Link className="button secondary" to="/projects">All projects</Link>
      </header>
      <section className="intake-summary" aria-label="Project intake summary">
        <article><span>Deadline</span><strong>{project.data.deadline ?? "Not set"}</strong></article>
        <article><span>Team</span><strong>{project.data.team_size} people</strong></article>
        <article><span>Capacity</span><strong>{Number(project.data.capacity_hours_per_week)} h/week</strong></article>
        <article><span>Timezone</span><strong>{project.data.timezone}</strong></article>
      </section>
      <section className="detail-panel">
        <div><span className="eyebrow">Requirements</span><h2>Captured scope</h2></div>
        {project.data.requirements.length ? <ul>{project.data.requirements.map((item) => <li key={item.id}><span className={`requirement-kind ${item.kind}`}>{item.kind}</span>{item.text}</li>)}</ul> : <p>No explicit features were added. The planning workflow can ask for clarification.</p>}
      </section>
      <section className="next-panel"><div><span className="eyebrow">Next phase capability</span><h2>Ready for AI-generated draft plans</h2><p>Schema-constrained planning workflows and atomic draft persistence arrive in Phase 5.</p></div><span className="phase-number" aria-label="Phase 5">05</span></section>
    </div>
  );
}
