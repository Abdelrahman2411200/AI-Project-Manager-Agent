import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { answerClarifications, getAgentRun, listClarifications, runKeys } from "../api/runs";
import { getProject, projectKeys } from "../api/projects";
import { errorMessage, isPermissionError } from "../api/errorUtils";
import { ErrorState, FeedbackBanner, LoadingState } from "../components/Feedback";
import { Clarifications } from "../features/planning/Clarifications";

export function ClarificationsPage() {
  const { projectId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const runId = searchParams.get("run") ?? "";
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const project = useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId),
  });
  const run = useQuery({
    queryKey: runKeys.detail(runId),
    queryFn: () => getAgentRun(runId),
    enabled: Boolean(runId),
  });
  const questions = useQuery({
    queryKey: runKeys.clarifications(projectId, runId),
    queryFn: () => listClarifications(projectId, runId),
    enabled: Boolean(projectId && runId),
  });
  const answer = useMutation({
    mutationFn: (answers: Array<{ question_id: string; answer: unknown }>) =>
      answerClarifications(projectId, runId, answers),
    onSuccess: (result) => {
      queryClient.setQueryData(runKeys.detail(runId), result.run);
      queryClient.setQueryData(runKeys.clarifications(projectId, runId), result.questions);
      try {
        sessionStorage.removeItem(`apm:clarifications:${projectId}:${runId}`);
      } catch {
        // Storage may be disabled.
      }
      if (result.resumed) {
        void navigate(`/projects/${projectId}/planning?run=${runId}`, { replace: true });
      }
    },
  });

  if (!runId) {
    return (
      <ErrorState
        title="Planning run reference missing"
        detail="Open clarifications from an active planning run so answers are attached to the correct workflow."
      />
    );
  }
  if (project.isPending || run.isPending || questions.isPending) {
    return <LoadingState title="Loading clarification questions…" detail="Restoring any answers saved in this browser." />;
  }
  const queryError = project.error ?? run.error ?? questions.error;
  if (queryError) {
    return (
      <ErrorState
        title={isPermissionError(queryError) ? "Clarifications unavailable" : "Questions could not be loaded"}
        detail={
          isPermissionError(queryError)
            ? "This planning run does not exist, or your account cannot access it."
            : errorMessage(queryError, "Try loading the decision checkpoint again.")
        }
        onRetry={() => {
          void project.refetch();
          void run.refetch();
          void questions.refetch();
        }}
      />
    );
  }
  if (!project.data || !run.data || !questions.data) return null;

  return (
    <div className="page-stack clarification-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
        <Link to={`/projects/${projectId}`}>{project.data.name}</Link><span aria-hidden="true">/</span>
        <Link to={`/projects/${projectId}/planning?run=${runId}`}>Planning</Link><span aria-hidden="true">/</span>
        <span aria-current="page">Clarifications</span>
      </nav>
      <header className="page-header">
        <div>
          <span className="eyebrow">Human decision checkpoint</span>
          <h1>Clarify {project.data.name}</h1>
          <p>Answer only what the project has not already established. Assumptions remain visible and reviewable.</p>
        </div>
        <Link className="button secondary" to={`/projects/${projectId}/planning?run=${runId}`}>Back to progress</Link>
      </header>
      {run.data.status !== "waiting_for_user" && run.data.status !== "queued" ? (
        <FeedbackBanner tone="info" title="This checkpoint is no longer accepting answers">
          The planning run is currently {run.data.status.replaceAll("_", " ")}.
        </FeedbackBanner>
      ) : null}
      {questions.data.length ? (
        <Clarifications
          projectId={projectId}
          runId={runId}
          questions={questions.data}
          pending={answer.isPending}
          error={answer.isError ? errorMessage(answer.error, "Review the answers and try again.") : undefined}
          onSubmit={(values) => answer.mutate(values)}
        />
      ) : (
        <section className="empty-panel">
          <span className="state-icon success" aria-hidden="true">✓</span>
          <h2>No clarification questions remain</h2>
          <p>The workflow already has enough project facts to continue planning.</p>
          <Link className="button primary" to={`/projects/${projectId}/planning?run=${runId}`}>Return to planning</Link>
        </section>
      )}
    </div>
  );
}
