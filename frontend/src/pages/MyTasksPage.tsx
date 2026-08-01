import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { getExecutionBoard } from "../api/execution";
import { listProjects } from "../api/projects";
import type { ProjectView, TaskExecutionView, TaskStatus } from "../api/types";
import { ErrorState, LoadingState, StateBadge } from "../components/Feedback";

type TaskFilter = "active" | TaskStatus | "all";

interface WorkspaceTask extends TaskExecutionView {
  project_name: string;
  version_number: number;
}

interface TaskWorkspace {
  projects: ProjectView[];
  tasks: WorkspaceTask[];
  projectsWithoutActivePlans: number;
}

async function loadTaskWorkspace(): Promise<TaskWorkspace> {
  const projects = (await listProjects()).items.filter((project) => project.status === "active");
  const results = await Promise.all(
    projects.map(async (project) => {
      try {
        return { project, board: await getExecutionBoard(project.id) };
      } catch (error) {
        if (error instanceof ApiError && error.problem.status === 404) return null;
        throw error;
      }
    }),
  );
  const active = results.filter((item) => item !== null);
  const tasks = active
    .flatMap(({ project, board }) =>
      board.tasks.map((task) => ({
        ...task,
        project_name: project.name,
        version_number: board.version_number,
      })),
    )
    .sort((left, right) => {
      const statusOrder: Record<TaskStatus, number> = {
        blocked: 0,
        in_progress: 1,
        ready: 2,
        pending: 3,
        completed: 4,
        cancelled: 5,
      };
      return (
        statusOrder[left.status] - statusOrder[right.status] ||
        Number(right.priority_score) - Number(left.priority_score) ||
        left.stable_key.localeCompare(right.stable_key)
      );
    });
  return {
    projects,
    tasks,
    projectsWithoutActivePlans: projects.length - active.length,
  };
}

export function MyTasksPage() {
  const [filter, setFilter] = useState<TaskFilter>("active");
  const workspace = useQuery({
    queryKey: ["workspace", "my-tasks"],
    queryFn: loadTaskWorkspace,
  });
  const visibleTasks = useMemo(() => {
    if (!workspace.data) return [];
    if (filter === "all") return workspace.data.tasks;
    if (filter === "active") {
      return workspace.data.tasks.filter(
        (task) => !["completed", "cancelled"].includes(task.status),
      );
    }
    return workspace.data.tasks.filter((task) => task.status === filter);
  }, [filter, workspace.data]);

  if (workspace.isPending) {
    return <LoadingState title="Loading your active-plan tasks…" />;
  }
  if (workspace.isError) {
    return (
      <ErrorState
        title="My tasks are unavailable"
        detail="The active project plans could not be loaded."
        onRetry={() => void workspace.refetch()}
      />
    );
  }

  const activeCount = workspace.data.tasks.filter(
    (task) => !["completed", "cancelled"].includes(task.status),
  ).length;
  const readyCount = workspace.data.tasks.filter((task) => task.status === "ready").length;
  const blockedCount = workspace.data.tasks.filter((task) => task.status === "blocked").length;

  return (
    <div className="page-stack workspace-index-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Owner workspace · active plans</span>
          <h1>My tasks</h1>
          <p>See the executable work from every approved and active project plan.</p>
        </div>
        <Link className="button secondary" to="/projects">Manage projects</Link>
      </header>

      <section className="workspace-summary-grid" aria-label="Task summary">
        <article><span>Active tasks</span><strong>{activeCount}</strong></article>
        <article><span>Ready to start</span><strong>{readyCount}</strong></article>
        <article><span>Blocked</span><strong>{blockedCount}</strong></article>
        <article><span>Active plans</span><strong>{workspace.data.projects.length - workspace.data.projectsWithoutActivePlans}</strong></article>
      </section>

      <section aria-labelledby="my-task-list-heading">
        <div className="section-heading split workspace-filter-heading">
          <div><span className="eyebrow">Prioritized work</span><h2 id="my-task-list-heading">Tasks across projects</h2></div>
          <label className="workspace-filter">
            Show
            <select value={filter} onChange={(event) => setFilter(event.target.value as TaskFilter)}>
              <option value="active">Active</option>
              <option value="ready">Ready</option>
              <option value="in_progress">In progress</option>
              <option value="blocked">Blocked</option>
              <option value="pending">Pending</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
              <option value="all">All</option>
            </select>
          </label>
        </div>

        {visibleTasks.length ? (
          <ul className="workspace-task-list">
            {visibleTasks.map((task) => (
              <li key={task.task_id} className="workspace-task-card">
                <div className="workspace-task-main">
                  <div className="title-with-badge">
                    <span className="task-key">{task.stable_key}</span>
                    <StateBadge state={task.status} />
                  </div>
                  <h3>{task.title}</h3>
                  <p>{task.deliverable}</p>
                  <div className="workspace-task-context">
                    <Link to={`/projects/${task.project_id}`}>{task.project_name}</Link>
                    <span>Plan v{task.version_number}</span>
                    <span>{task.milestone_key} · {task.milestone_name}</span>
                  </div>
                </div>
                <dl className="workspace-task-metrics">
                  <div><dt>Priority</dt><dd>{task.priority_label} · {Number(task.priority_score).toFixed(1)}</dd></div>
                  <div><dt>Progress</dt><dd>{Math.round(Number(task.progress_fraction) * 100)}%</dd></div>
                  <div><dt>Planned finish</dt><dd>{task.planned_finish ?? "Not scheduled"}</dd></div>
                </dl>
                <Link className="button compact secondary" to={`/projects/${task.project_id}/board`}>Open project board</Link>
              </li>
            ))}
          </ul>
        ) : (
          <div className="content-state compact-state">
            <h3>{workspace.data.tasks.length ? "No tasks match this filter" : "No active-plan tasks yet"}</h3>
            <p>
              {workspace.data.tasks.length
                ? "Choose another task status to see more work."
                : "Generate a plan, review it, and explicitly activate it before tasks enter execution."}
            </p>
            {!workspace.data.tasks.length ? <Link className="button primary" to="/projects">Open projects</Link> : null}
          </div>
        )}
      </section>
    </div>
  );
}
