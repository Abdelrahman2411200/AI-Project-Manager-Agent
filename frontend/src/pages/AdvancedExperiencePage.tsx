import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { errorMessage, isPermissionError } from "../api/errorUtils";
import { getPlanVersion, listPlanVersions, planKeys } from "../api/plans";
import { getProject, projectKeys } from "../api/projects";
import { ErrorState, LoadingState, StateBadge } from "../components/Feedback";
import { EvaluationDashboard } from "../features/advanced/EvaluationDashboard";
import { RiskRegister } from "../features/advanced/RiskRegister";
import { ScheduleTimeline } from "../features/advanced/ScheduleTimeline";
import { ExecutionNav } from "../features/execution/ExecutionNav";

const DependencyGraph = lazy(async () => {
  const module = await import("../features/advanced/DependencyGraph");
  return { default: module.DependencyGraph };
});

export function AdvancedExperiencePage() {
  const { projectId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
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
  const requestedId = searchParams.get("version");
  const selected =
    versions.data?.find((item) => item.id === requestedId) ??
    versions.data?.find((item) => item.state === "active") ??
    versions.data?.[0];
  const plan = useQuery({
    queryKey: planKeys.detail(selected?.id ?? ""),
    queryFn: () => getPlanVersion(selected?.id ?? ""),
    enabled: Boolean(selected?.id),
  });

  if (project.isPending || versions.isPending || (selected && plan.isPending)) {
    return (
      <LoadingState
        title="Loading full-version intelligence…"
        detail="Reading the selected immutable plan, schedule, dependencies, risks, and evaluation evidence."
      />
    );
  }
  const queryError = project.error ?? versions.error ?? plan.error;
  if (queryError) {
    return (
      <ErrorState
        title={isPermissionError(queryError) ? "Intelligence unavailable" : "Full-version experience could not load"}
        detail={errorMessage(queryError, "Open the project again or select another plan version.")}
        onRetry={() => {
          void project.refetch();
          void versions.refetch();
          void plan.refetch();
        }}
      />
    );
  }
  if (!project.data) return null;
  if (!selected || !plan.data) {
    return (
      <div className="page-stack">
        <nav className="breadcrumbs" aria-label="Breadcrumb">
          <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
          <Link to={`/projects/${projectId}`}>{project.data.name}</Link><span aria-hidden="true">/</span>
          <span aria-current="page">Intelligence</span>
        </nav>
        <ErrorState
          title="No plan version to analyze"
          detail="Complete planning to unlock dependencies, timeline, risks, scenarios, and evaluation evidence."
        />
      </div>
    );
  }

  return (
    <div className="page-stack advanced-experience-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
        <Link to={`/projects/${projectId}`}>{project.data.name}</Link><span aria-hidden="true">/</span>
        <span aria-current="page">Intelligence</span>
      </nav>
      <header className="page-header advanced-experience-header">
        <div>
          <span className="eyebrow">Full-version experience · deterministic results</span>
          <h1>{project.data.name} intelligence</h1>
          <p>
            Inspect the version-local dependency graph, persisted schedule, risk register,
            virtual scenarios, and reviewed release evidence.
          </p>
        </div>
        <div className="header-actions">
          <StateBadge state={plan.data.state} />
          <Link className="button" to={`/projects/${projectId}/scenarios/new`}>
            Run scenario
          </Link>
        </div>
      </header>
      <ExecutionNav projectId={projectId} />

      <div className="advanced-toolbar">
        <label>
          <span>Plan version</span>
          <select
            value={selected.id}
            onChange={(event) => setSearchParams({ version: event.target.value })}
          >
            {(versions.data ?? []).map((item) => (
              <option value={item.id} key={item.id}>
                Version {item.number} · {item.state.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <nav aria-label="Intelligence sections">
          <a href="#dependencies">Dependencies</a>
          <a href="#timeline">Timeline</a>
          <a href="#risks">Risks</a>
          <a href="#evaluation">Evaluation</a>
        </nav>
      </div>

      <div id="dependencies">
        <Suspense
          fallback={
            <LoadingState
              title="Loading dependency visualization…"
              detail="The heavy graph bundle is loaded only for this view."
            />
          }
        >
          <DependencyGraph plan={plan.data} />
        </Suspense>
      </div>
      <div id="timeline">
        <ScheduleTimeline plan={plan.data} />
      </div>
      <div id="risks">
        <RiskRegister plan={plan.data} />
      </div>
      <div id="evaluation">
        <EvaluationDashboard />
      </div>

      <footer className="calculation-footer">
        <strong>Selected plan</strong>
        <span>Version {plan.data.number} · {plan.data.state.replaceAll("_", " ")}</span>
        <code>{plan.data.content_hash}</code>
      </footer>
    </div>
  );
}
