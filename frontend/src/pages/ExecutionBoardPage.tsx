import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { useExecutionBoard, useExecutionMutations } from "../api/execution";
import { errorMessage } from "../api/errorUtils";
import { getProject, projectKeys } from "../api/projects";
import { ErrorState, LoadingState } from "../components/Feedback";
import { ActivityList } from "../features/execution/ActivityList";
import { ExecutionBoard } from "../features/execution/ExecutionBoard";
import { ExecutionNav } from "../features/execution/ExecutionNav";
import { HealthSummary } from "../features/execution/HealthSummary";

export function ExecutionBoardPage() {
  const { projectId = "" } = useParams();
  const project = useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId),
  });
  const board = useExecutionBoard(projectId);
  const mutations = useExecutionMutations(projectId);

  if (project.isPending || board.isPending) {
    return <LoadingState title="Loading active execution…" detail="Recalculating readiness, progress, schedule, and health from persisted events." />;
  }
  if (project.isError) {
    return <ErrorState title="Project unavailable" detail="This project does not exist or is unavailable to your account." />;
  }
  if (board.isError) {
    return (
      <ErrorState
        title="Active execution is not available"
        detail={errorMessage(board.error, "Approve and activate a project plan before managing task execution.")}
        onRetry={() => void board.refetch()}
      />
    );
  }
  const taskKeys = new Map(board.data.tasks.map((task) => [task.task_id, task.stable_key]));

  return (
    <div className="page-stack execution-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
        <Link to={`/projects/${projectId}`}>{project.data.name}</Link><span aria-hidden="true">/</span>
        <span aria-current="page">Board</span>
      </nav>
      <header className="page-header execution-header">
        <div>
          <span className="eyebrow">Active execution · version {board.data.version_number}</span>
          <h1>{project.data.name} execution board</h1>
          <p>Move work through legal states, preserve immutable history, and see deterministic project effects immediately.</p>
        </div>
        <button className="button secondary" type="button" disabled={board.isFetching} onClick={() => void board.refetch()}>
          {board.isFetching ? "Refreshing…" : "Refresh state"}
        </button>
      </header>
      <ExecutionNav projectId={projectId} />
      <HealthSummary projectId={projectId} health={board.data.health} progress={board.data.progress} />
      <ExecutionBoard
        board={board.data}
        mutations={mutations}
        onReload={() => void board.refetch()}
      />
      <ActivityList events={board.data.recent_events} taskKeys={taskKeys} />
    </div>
  );
}
