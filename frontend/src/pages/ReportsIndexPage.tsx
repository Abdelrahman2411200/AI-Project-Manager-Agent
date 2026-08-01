import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listReports } from "../api/insights";
import { listProjects } from "../api/projects";
import type { ProjectView, ReportSummaryView } from "../api/types";
import { ErrorState, LoadingState, StateBadge } from "../components/Feedback";

interface WorkspaceReport extends ReportSummaryView {
  project_name: string;
}

interface ReportsWorkspace {
  projects: Array<{ project: ProjectView; reportCount: number }>;
  reports: WorkspaceReport[];
}

async function loadReportsWorkspace(): Promise<ReportsWorkspace> {
  const projects = (await listProjects()).items;
  const grouped = await Promise.all(
    projects.map(async (project) => ({ project, reports: await listReports(project.id) })),
  );
  return {
    projects: grouped.map(({ project, reports }) => ({ project, reportCount: reports.length })),
    reports: grouped
      .flatMap(({ project, reports }) =>
        reports.map((report) => ({ ...report, project_name: project.name })),
      )
      .sort((left, right) => right.created_at.localeCompare(left.created_at)),
  };
}

export function ReportsIndexPage() {
  const workspace = useQuery({
    queryKey: ["workspace", "reports"],
    queryFn: loadReportsWorkspace,
  });

  if (workspace.isPending) return <LoadingState title="Loading report workspaces…" />;
  if (workspace.isError) {
    return (
      <ErrorState
        title="Reports are unavailable"
        detail="The report history for your projects could not be loaded."
        onRetry={() => void workspace.refetch()}
      />
    );
  }

  return (
    <div className="page-stack workspace-index-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Persisted facts · all projects</span>
          <h1>Reports</h1>
          <p>Open factual report history or choose a project to generate a new report.</p>
        </div>
        <Link className="button secondary" to="/projects">Manage projects</Link>
      </header>

      <section aria-labelledby="report-workspaces-heading">
        <div className="section-heading split">
          <div><span className="eyebrow">Project workspaces</span><h2 id="report-workspaces-heading">Generate by project</h2></div>
          <span>{workspace.data.projects.length} project{workspace.data.projects.length === 1 ? "" : "s"}</span>
        </div>
        {workspace.data.projects.length ? (
          <ul className="workspace-project-list">
            {workspace.data.projects.map(({ project, reportCount }) => (
              <li key={project.id}>
                <div><h3>{project.name}</h3><p>{reportCount} generated report{reportCount === 1 ? "" : "s"}</p></div>
                <Link className="button compact secondary" to={`/projects/${project.id}/reports`}>Open reports</Link>
              </li>
            ))}
          </ul>
        ) : (
          <div className="content-state compact-state"><h3>No projects yet</h3><p>Create a project before generating factual reports.</p><Link className="button primary" to="/projects/new">Create project</Link></div>
        )}
      </section>

      <section aria-labelledby="all-report-history-heading">
        <div className="section-heading split">
          <div><span className="eyebrow">Immutable history</span><h2 id="all-report-history-heading">Generated reports</h2></div>
          <span>{workspace.data.reports.length} report{workspace.data.reports.length === 1 ? "" : "s"}</span>
        </div>
        {workspace.data.reports.length ? (
          <ul className="report-list">
            {workspace.data.reports.map((report) => (
              <li key={report.id}>
                <div>
                  <span className="task-key">{report.report_type.toUpperCase()}</span>
                  <h3><Link to={`/reports/${report.id}`}>{report.project_name}</Link></h3>
                  <p>{report.period_start} to {report.period_end}</p>
                  <time dateTime={report.created_at}>Generated {new Date(report.created_at).toLocaleString()}</time>
                </div>
                <div><StateBadge state={report.status} /><code>{report.content_hash.slice(0, 18)}…</code></div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="content-state compact-state"><h3>No reports yet</h3><p>Activate a project plan, then open its report workspace to generate the first factual report.</p></div>
        )}
      </section>
    </div>
  );
}
