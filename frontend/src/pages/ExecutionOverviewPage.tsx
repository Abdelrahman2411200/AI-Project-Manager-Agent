import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { useExecutionBoard } from "../api/execution";
import { errorMessage } from "../api/errorUtils";
import { getProject, projectKeys } from "../api/projects";
import { ErrorState, LoadingState, StateBadge } from "../components/Feedback";
import { ActivityList } from "../features/execution/ActivityList";
import { ExecutionNav } from "../features/execution/ExecutionNav";
import { HealthSummary } from "../features/execution/HealthSummary";

function percent(value: string | null): string {
  return value === null ? "—" : `${Math.round(Number(value) * 100)}%`;
}

export function ExecutionOverviewPage() {
  const { projectId = "" } = useParams();
  const project = useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId),
  });
  const board = useExecutionBoard(projectId);

  if (project.isPending || board.isPending) return <LoadingState title="Loading project overview…" />;
  if (project.isError) return <ErrorState title="Project unavailable" detail="This project does not exist or is unavailable to your account." />;
  if (board.isError) {
    return (
      <section className="content-state">
        <span className="state-icon" aria-hidden="true">→</span>
        <h1>Activate a plan to begin execution</h1>
        <p>{errorMessage(board.error, "This project has no active plan yet.")}</p>
        <Link className="button primary" to={`/projects/${projectId}`}>Return to project</Link>
      </section>
    );
  }

  const tasks = board.data.tasks;
  const counts = new Map(tasks.map((task) => [task.status, tasks.filter((item) => item.status === task.status).length]));
  const ready = tasks.filter((task) => task.status === "ready");
  const blocked = tasks.filter((task) => task.status === "blocked");
  const nextTask = ready[0];
  const taskKeys = new Map(tasks.map((task) => [task.task_id, task.stable_key]));

  return (
    <div className="page-stack execution-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
        <Link to={`/projects/${projectId}`}>{project.data.name}</Link><span aria-hidden="true">/</span>
        <span aria-current="page">Overview</span>
      </nav>
      <header className="page-header execution-header">
        <div>
          <span className="eyebrow">Active version {board.data.version_number}</span>
          <h1>{project.data.name} overview</h1>
          <p>Current projections are derived from the approved plan and immutable execution events.</p>
        </div>
        <Link className="button primary" to={`/projects/${projectId}/board`}>Open execution board</Link>
      </header>
      <ExecutionNav projectId={projectId} />
      <HealthSummary projectId={projectId} health={board.data.health} progress={board.data.progress} />

      <section className="overview-metrics" aria-label="Task status metrics">
        {(["ready", "in_progress", "blocked", "completed"] as const).map((status) => (
          <article key={status}>
            <StateBadge state={status} />
            <strong>{counts.get(status) ?? 0}</strong>
            <span>{status.replaceAll("_", " ")} tasks</span>
          </article>
        ))}
      </section>

      <div className="execution-overview-grid">
        <section className="detail-panel next-action-panel">
          <span className="eyebrow">Next action</span>
          {nextTask ? (
            <>
              <h2>{nextTask.stable_key} · {nextTask.title}</h2>
              <p>{nextTask.deliverable}</p>
              <dl>
                <div><dt>Priority</dt><dd>{nextTask.priority_label}</dd></div>
                <div><dt>Effort</dt><dd>{Number(nextTask.effort_likely_hours)} hours</dd></div>
                <div><dt>Milestone</dt><dd>{nextTask.milestone_key}</dd></div>
              </dl>
              <Link className="button primary" to={`/projects/${projectId}/board#task-${nextTask.stable_key}`}>Start from the board</Link>
            </>
          ) : blocked.length ? (
            <>
              <h2>Resolve {blocked.length} blocker{blocked.length === 1 ? "" : "s"}</h2>
              <p>No task is currently ready. Inspect the blocked work and its dependency evidence.</p>
              <Link className="button secondary" to={`/projects/${projectId}/board`}>Inspect blockers</Link>
            </>
          ) : (
            <>
              <h2>No ready work</h2>
              <p>All work is complete or waiting for prerequisite events.</p>
            </>
          )}
        </section>
        <section className="detail-panel metric-definition-panel">
          <span className="eyebrow">Metric definition</span>
          <h2>Truthful weighted progress</h2>
          <p>Only leaf tasks contribute. Completed work counts as 100%; in-progress and blocked work uses the latest explicit fraction. Cancelled work is excluded.</p>
          <dl>
            <div><dt>Current</dt><dd>{percent(board.data.progress.project.fraction)}</dd></div>
            <div><dt>Estimated leaves</dt><dd>{board.data.progress.project.active_leaf_count - board.data.progress.project.unestimated_leaf_count}</dd></div>
            <div><dt>Calculation</dt><dd>{board.data.progress.calculation_version}</dd></div>
          </dl>
        </section>
      </div>
      <ActivityList events={board.data.recent_events.slice(0, 8)} taskKeys={taskKeys} />
    </div>
  );
}
