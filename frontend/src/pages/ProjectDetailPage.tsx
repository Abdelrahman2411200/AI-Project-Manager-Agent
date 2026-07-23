import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { listPlanVersions, planKeys } from "../api/plans";
import { getProject, projectKeys } from "../api/projects";
import { ErrorState, LoadingState, StateBadge } from "../components/Feedback";

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const project = useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId),
  });
  const versions = useQuery({
    queryKey: planKeys.project(projectId),
    queryFn: () => listPlanVersions(projectId),
    enabled: Boolean(projectId),
  });

  if (project.isPending) {
    return <LoadingState title="Loading project…" />;
  }
  if (project.isError) {
    return <ErrorState title="Project unavailable" detail="This project could not be loaded or is not available to your account." />;
  }
  const latestVersion = versions.data?.[0];
  const activeVersion = versions.data?.find((version) => version.state === "active");

  return (
    <div className="page-stack">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
        <span aria-current="page">{project.data.name}</span>
      </nav>
      <header className="page-header">
        <div><span className="eyebrow">Owner project · intake version {project.data.row_version}</span><h1>{project.data.name}</h1><p>{project.data.goal}</p></div>
        <div className="header-actions">
          <Link className="button secondary" to="/projects">All projects</Link>
          <Link className="button primary" to={`/projects/${projectId}/planning`}>Start planning run</Link>
        </div>
      </header>
      <section className="intake-summary" aria-label="Project intake summary">
        <article><span>Deadline</span><strong>{project.data.deadline ?? "Not set"}</strong></article>
        <article><span>Team</span><strong>{project.data.team_size} people</strong></article>
        <article><span>Capacity</span><strong>{Number(project.data.capacity_hours_per_week)} h/week</strong></article>
        <article><span>Timezone</span><strong>{project.data.timezone}</strong></article>
      </section>

      <div className="project-detail-grid">
        <section className="detail-panel">
          <div><span className="eyebrow">Requirements</span><h2>Captured scope</h2></div>
          {project.data.requirements.length ? <ul>{project.data.requirements.map((item) => <li key={item.id}><span className={`requirement-kind ${item.kind}`}>{item.kind}</span>{item.text}</li>)}</ul> : <p>No explicit features were added. The planning workflow can ask for clarification.</p>}
        </section>
        <section className="detail-panel">
          <div><span className="eyebrow">Constraints</span><h2>Delivery boundaries</h2></div>
          {project.data.constraints.length ? (
            <ul>{project.data.constraints.map((item) => <li key={item.id}><span className="requirement-kind">{item.constraint_type}</span>{typeof item.value_json.text === "string" ? item.value_json.text : "Structured constraint"}</li>)}</ul>
          ) : <p>No delivery constraints were recorded.</p>}
        </section>
      </div>

      <section className="plan-entry-panel" aria-labelledby="plan-entry-title">
        <div>
          <span className="eyebrow">{activeVersion ? "Active plan" : latestVersion ? "Planning in progress" : "Next step"}</span>
          <div className="title-with-badge">
            <h2 id="plan-entry-title">{activeVersion ? `Version ${activeVersion.number} is active` : latestVersion ? `Continue version ${latestVersion.number}` : "Build the first project plan"}</h2>
            {activeVersion || latestVersion ? <StateBadge state={(activeVersion ?? latestVersion)?.state ?? "draft"} /> : null}
          </div>
          <p>
            {activeVersion
              ? "The approved version is immutable and available for inspection."
              : latestVersion
                ? "Review generated milestones, tasks, estimates, dependencies, scope, and validation evidence."
                : "Start the structured workflow. It pauses for missing decisions and never activates a plan without owner approval."}
          </p>
        </div>
        <div className="header-actions">
          {latestVersion ? <Link className="button primary" to={`/projects/${projectId}/plan/${latestVersion.id}/review`}>Open plan review</Link> : <Link className="button primary" to={`/projects/${projectId}/planning`}>Start planning</Link>}
          {activeVersion && latestVersion?.id !== activeVersion.id ? <Link className="button secondary" to={`/projects/${projectId}/plan/${activeVersion.id}/review`}>View active version</Link> : null}
        </div>
      </section>
    </div>
  );
}
