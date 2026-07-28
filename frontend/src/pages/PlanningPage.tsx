import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { getSystemCapabilities, operationsKeys } from "../api/operations";
import { cancelAgentRun, getAgentRun, listAgentRunSteps, planningRunPollInterval, runKeys, startPlanningRun } from "../api/runs";
import { getProject, projectKeys } from "../api/projects";
import { errorMessage, isPermissionError } from "../api/errorUtils";
import { ErrorState, FeedbackBanner, LoadingState } from "../components/Feedback";
import { RunProgress } from "../features/planning/RunProgress";

function planningStartErrorFromState(state: unknown): string | null {
  if (typeof state !== "object" || state === null || !("planningStartError" in state)) {
    return null;
  }
  const value = (state as Record<string, unknown>).planningStartError;
  return typeof value === "string" ? value : null;
}

export function PlanningPage() {
  const { projectId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const runId = searchParams.get("run") ?? "";
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const navigationStartError = planningStartErrorFromState(location.state as unknown);
  const project = useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId),
  });
  const run = useQuery({
    queryKey: runKeys.detail(runId),
    queryFn: () => getAgentRun(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => planningRunPollInterval(query.state.data),
  });
  const steps = useQuery({
    queryKey: runKeys.steps(runId),
    queryFn: () => listAgentRunSteps(runId),
    enabled: Boolean(runId),
    refetchInterval: () =>
      run.data && planningRunPollInterval(run.data) !== false ? 1_000 : false,
  });
  const capabilities = useQuery({
    queryKey: operationsKeys.capabilities,
    queryFn: getSystemCapabilities,
    enabled:
      (!runId && project.data?.status === "active") ||
      run.data?.outcome?.failure_code === "AI_UNCONFIGURED",
    refetchInterval: (query) =>
      query.state.data?.planning_ai_configured === true ? false : 5_000,
  });
  const planningAiConfigured = capabilities.data?.planning_ai_configured === true;
  const start = useMutation({
    mutationFn: () => startPlanningRun(projectId),
    onSuccess: (createdRun) => {
      queryClient.setQueryData(runKeys.detail(createdRun.id), createdRun);
      void navigate(`/projects/${projectId}/planning?run=${createdRun.id}`, { replace: true });
    },
  });
  const cancel = useMutation({
    mutationFn: () => cancelAgentRun(runId),
    onSuccess: (cancelledRun) => {
      queryClient.setQueryData(runKeys.detail(runId), cancelledRun);
    },
  });
  const permissionFailure = useMemo(
    () => isPermissionError(project.error) || isPermissionError(run.error),
    [project.error, run.error],
  );

  if (project.isPending || (runId && run.isPending)) {
    return <LoadingState title="Opening planning workspace…" detail="Loading the latest owner-scoped run state." />;
  }
  if (permissionFailure) {
    return (
      <ErrorState
        title="Planning workspace unavailable"
        detail="This project or run does not exist, or your account does not have permission to view it."
      />
    );
  }
  if (project.isError || (runId && run.isError)) {
    return (
      <ErrorState
        title="Planning workspace unavailable"
        detail={errorMessage(project.error ?? run.error, "The planning data could not be loaded.")}
        onRetry={() => {
          void project.refetch();
          if (runId) void run.refetch();
        }}
      />
    );
  }
  if (!project.data) return null;

  if (!runId) {
    if (project.data.status === "archived") {
      return (
        <div className="page-stack planning-page">
          <nav className="breadcrumbs" aria-label="Breadcrumb">
            <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
            <Link to={`/projects/${projectId}`}>{project.data.name}</Link><span aria-hidden="true">/</span>
            <span aria-current="page">Planning</span>
          </nav>
          <ErrorState
            title="Planning is unavailable for archived projects"
            detail="Choose an active project or create a new project before starting a planning run."
            actions={<Link className="button primary" to="/projects">Choose an active project</Link>}
          />
        </div>
      );
    }
    return (
      <div className="page-stack planning-page">
        <nav className="breadcrumbs" aria-label="Breadcrumb">
          <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
          <Link to={`/projects/${projectId}`}>{project.data.name}</Link><span aria-hidden="true">/</span>
          <span aria-current="page">Planning</span>
        </nav>
        <section className="planning-launch">
          <div className="launch-mark" aria-hidden="true">AI</div>
          <span className="eyebrow">Structured planning workflow</span>
          <h1>Turn the project intake into an actionable plan</h1>
          <p>
            The workflow will identify missing decisions, then generate milestones, leaf tasks,
            estimates, dependencies, a schedule, risks, and a deterministic quality report.
          </p>
          {navigationStartError || start.isError ? (
            <FeedbackBanner tone="danger" title="Planning could not start">
              {navigationStartError ??
                errorMessage(start.error, "Try starting the planning run again.")}
            </FeedbackBanner>
          ) : null}
          {capabilities.isError ? (
            <FeedbackBanner
              tone="danger"
              title="Planning availability could not be checked"
              actions={
                <button
                  className="button compact secondary"
                  type="button"
                  onClick={() => void capabilities.refetch()}
                >
                  Check again
                </button>
              }
            >
              The server did not return its AI-planning status. Starting a run is disabled until
              the check succeeds.
            </FeedbackBanner>
          ) : null}
          {!capabilities.isPending && !capabilities.isError && !planningAiConfigured ? (
            <FeedbackBanner tone="warning" title="AI planning needs server configuration">
              Ask the server operator to configure OPENAI_API_KEY and restart the API and worker.
              You can still review this project while planning is unavailable.
            </FeedbackBanner>
          ) : null}
          <div className="launch-checklist" aria-label="Planning safeguards">
            <span>Schema-constrained output</span>
            <span>Deterministic validation</span>
            <span>Owner approval required</span>
          </div>
          <button
            className="button primary"
            type="button"
            disabled={start.isPending || capabilities.isPending || !planningAiConfigured}
            onClick={() => start.mutate()}
          >
            {start.isPending
              ? "Starting planning…"
              : capabilities.isPending
                ? "Checking AI planning…"
                : planningAiConfigured
                  ? "Start planning"
                  : "AI planning unavailable"}
          </button>
        </section>
      </div>
    );
  }

  if (!run.data) return null;
  const rawFailureCode =
    run.data.outcome && typeof run.data.outcome.failure_code === "string"
      ? run.data.outcome.failure_code
      : null;
  const failureDetail =
    rawFailureCode === "AI_UNCONFIGURED"
      ? planningAiConfigured
        ? "OpenAI is now configured. This failed run remains as an audit record; start a new planning run to continue."
        : "OpenAI is not configured for this environment. Add OPENAI_API_KEY and restart the API and worker before starting another planning run."
      : rawFailureCode === "MODEL_QUOTA_EXHAUSTED"
        ? "The OpenAI API account has no available quota. Add API billing or credits, or raise the OpenAI project usage limit, before starting another planning run."
      : rawFailureCode
        ? `The workflow reported ${rawFailureCode.replaceAll("_", " ")}. No incomplete plan was activated.`
        : "The workflow could not produce a valid plan. No incomplete plan was activated.";

  return (
    <div className="page-stack planning-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
        <Link to={`/projects/${projectId}`}>{project.data.name}</Link><span aria-hidden="true">/</span>
        <span aria-current="page">Planning run</span>
      </nav>
      <header className="page-header">
        <div>
          <span className="eyebrow">AI-assisted · owner controlled</span>
          <h1>{project.data.name}</h1>
          <p>Review workflow progress and respond when a decision checkpoint needs you.</p>
        </div>
        <Link className="button secondary" to={`/projects/${projectId}`}>Project overview</Link>
      </header>

      {run.data.status === "waiting_for_user" ? (
        <FeedbackBanner
          tone="warning"
          title="Planning is waiting for your decisions"
          actions={<Link className="button primary" to={`/projects/${projectId}/clarify?run=${runId}`}>Answer questions</Link>}
        >
          Required project facts are missing. The workflow will remain paused until you answer or
          explicitly accept available assumptions.
        </FeedbackBanner>
      ) : null}
      {run.data.status === "completed" && run.data.proposed_plan_version_id ? (
        <FeedbackBanner
          tone="success"
          title="Your draft plan is ready for review"
          actions={
            <Link
              className="button primary"
              to={`/projects/${projectId}/plan/${run.data.proposed_plan_version_id}/review`}
            >
              Review draft plan
            </Link>
          }
        >
          Deterministic quality checks passed before this draft was persisted.
        </FeedbackBanner>
      ) : null}
      {run.data.status === "failed" ? (
        <FeedbackBanner
          tone={rawFailureCode === "AI_UNCONFIGURED" && planningAiConfigured ? "warning" : "danger"}
          title="Planning stopped safely"
          actions={
            rawFailureCode === "AI_UNCONFIGURED" && planningAiConfigured ? (
              <button
                className="button primary"
                type="button"
                disabled={start.isPending}
                onClick={() => start.mutate()}
              >
                {start.isPending ? "Starting a new run…" : "Start a new planning run"}
              </button>
            ) : undefined
          }
        >
          {failureDetail}
        </FeedbackBanner>
      ) : null}
      {run.data.status === "failed" && start.isError ? (
        <FeedbackBanner tone="danger" title="A new planning run could not start">
          {errorMessage(start.error, "Check the server configuration and try again.")}
        </FeedbackBanner>
      ) : null}
      {run.data.status === "partial" ? (
        <FeedbackBanner tone="warning" title="Planning saved a partial checkpoint">
          The available work is retained, but approval stays unavailable until planning completes.
        </FeedbackBanner>
      ) : null}
      {run.data.status === "cancelled" ? (
        <FeedbackBanner tone="info" title="Planning run cancelled">
          No active plan was changed. You can start a new run from the project overview.
        </FeedbackBanner>
      ) : null}
      {steps.isError ? (
        <FeedbackBanner
          tone="danger"
          title="Step details are temporarily unavailable"
          actions={<button className="button compact secondary" type="button" onClick={() => void steps.refetch()}>Retry</button>}
        />
      ) : null}
      <RunProgress
        run={run.data}
        steps={steps.data ?? []}
        cancelling={cancel.isPending}
        onCancel={() => cancel.mutate()}
      />
    </div>
  );
}
