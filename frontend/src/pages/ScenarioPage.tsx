import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { createScenario, useScenario } from "../api/advanced";
import { errorMessage, isPermissionError } from "../api/errorUtils";
import { listPlanVersions, planKeys } from "../api/plans";
import { getProject, projectKeys } from "../api/projects";
import { ErrorState, FeedbackBanner, LoadingState } from "../components/Feedback";
import { ExecutionNav } from "../features/execution/ExecutionNav";

function ResultTable({
  baseline,
  scenario,
}: {
  baseline: Record<string, unknown>;
  scenario: Record<string, unknown>;
}) {
  const display = (value: unknown) =>
    typeof value === "string" || typeof value === "number" || typeof value === "boolean"
      ? String(value)
      : value === null || value === undefined
        ? "Not available"
        : JSON.stringify(value);
  const rows = [
    ["Total effort", "total_effort_hours"],
    ["Weekly capacity", "capacity_hours_per_week"],
    ["Forecast weeks", "forecast_weeks"],
    ["Forecast finish", "forecast_finish"],
    ["Deadline delta days", "deadline_delta_days"],
    ["Critical path hours", "critical_path_hours"],
  ] as const;
  return (
    <div className="table-scroll" tabIndex={0}>
      <table>
        <caption>Baseline and virtual scenario metrics</caption>
        <thead><tr><th>Metric</th><th>Baseline</th><th>Scenario</th></tr></thead>
        <tbody>
          {rows.map(([label, key]) => (
            <tr key={key}>
              <th scope="row">{label}</th>
              <td>{display(baseline[key])}</td>
              <td>{display(scenario[key])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ScenarioPage() {
  const { projectId = "", scenarioId = "" } = useParams();
  const navigate = useNavigate();
  const creating = scenarioId === "new";
  const [name, setName] = useState("Capacity adjustment");
  const [capacity, setCapacity] = useState("40");
  const [deadline, setDeadline] = useState("");
  const project = useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId),
  });
  const versions = useQuery({
    queryKey: planKeys.project(projectId),
    queryFn: () => listPlanVersions(projectId),
    enabled: Boolean(projectId) && creating,
  });
  const scenario = useScenario(scenarioId);
  const create = useMutation({
    mutationFn: () => {
      const active = versions.data?.find((item) => item.state === "active");
      if (!active) throw new Error("Activate a plan before running a scenario.");
      return createScenario(projectId, {
        name,
        baseline_version_id: active.id,
        overrides: {
          capacity_hours_per_week: Number(capacity),
          ...(deadline ? { deadline } : {}),
        },
      });
    },
    onSuccess: (result) => navigate(`/projects/${projectId}/scenarios/${result.id}`),
  });

  if (project.isPending || (!creating && scenario.isPending)) {
    return <LoadingState title="Loading scenario…" detail="Reading the persisted baseline comparison." />;
  }
  const queryError = project.error ?? scenario.error;
  if (queryError) {
    return (
      <ErrorState
        title={isPermissionError(queryError) ? "Scenario unavailable" : "Scenario could not be loaded"}
        detail={errorMessage(queryError, "Try opening the scenario again.")}
      />
    );
  }
  if (!project.data) return null;

  return (
    <div className="page-stack scenario-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
        <Link to={`/projects/${projectId}`}>{project.data.name}</Link><span aria-hidden="true">/</span>
        <span aria-current="page">{creating ? "New scenario" : "Scenario result"}</span>
      </nav>
      <header className="page-header">
        <div>
          <span className="eyebrow">Virtual clone · active plan unchanged</span>
          <h1>{creating ? "Run a what-if scenario" : scenario.data?.name}</h1>
          <p>Inputs are validated, calculations are deterministic, and results are stored against the exact baseline content hash.</p>
        </div>
        {!creating ? <Link className="button secondary" to={`/projects/${projectId}/scenarios/new`}>New scenario</Link> : null}
      </header>
      <ExecutionNav projectId={projectId} />

      {creating ? (
        <section className="detail-panel scenario-form" aria-labelledby="scenario-input-title">
          <h2 id="scenario-input-title">Scenario inputs</h2>
          {!versions.data?.some((item) => item.state === "active") ? (
            <FeedbackBanner tone="warning" title="An active plan is required">
              Review and activate a plan before creating a virtual clone.
            </FeedbackBanner>
          ) : null}
          <label><span>Scenario name</span><input value={name} minLength={3} maxLength={120} onChange={(event) => setName(event.target.value)} /></label>
          <label><span>Weekly capacity hours</span><input type="number" min={1} max={10000} value={capacity} onChange={(event) => setCapacity(event.target.value)} /></label>
          <label><span>Optional deadline</span><input type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} /></label>
          {create.isError ? <FeedbackBanner tone="danger" title="Scenario could not run">{errorMessage(create.error, "Check the inputs and try again.")}</FeedbackBanner> : null}
          <button type="button" className="button" disabled={create.isPending || name.trim().length < 3 || Number(capacity) <= 0} onClick={() => create.mutate()}>
            {create.isPending ? "Calculating…" : "Run virtual scenario"}
          </button>
        </section>
      ) : scenario.data ? (
        <>
          <FeedbackBanner tone="info" title="Baseline remains unchanged">
            Scenario result is tied to <code>{scenario.data.baseline_content_hash}</code>. It has no write path to plan tables.
          </FeedbackBanner>
          <dl className="analysis-facts">
            <div><dt>Forecast delta</dt><dd>{scenario.data.result_json.delta.forecast_finish_days} days</dd></div>
            <div><dt>Effort delta</dt><dd>{scenario.data.result_json.delta.effort_hours} hours</dd></div>
            <div><dt>Critical-path delta</dt><dd>{scenario.data.result_json.delta.critical_path_hours} hours</dd></div>
            <div><dt>Status</dt><dd>{scenario.data.status.replaceAll("_", " ")}</dd></div>
          </dl>
          <section className="detail-panel">
            <h2>Metric comparison</h2>
            <ResultTable baseline={scenario.data.result_json.baseline} scenario={scenario.data.result_json.scenario} />
          </section>
          <section className="detail-panel">
            <h2>Grounded explanation</h2>
            <p>{scenario.data.explanation_json?.summary ?? "No narrative explanation is available."}</p>
            <small>Source: {scenario.data.explanation_json?.source ?? "none"} · calculation {scenario.data.calculation_version}</small>
          </section>
        </>
      ) : null}
    </div>
  );
}
