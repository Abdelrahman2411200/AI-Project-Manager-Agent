import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { useExecutionBoard } from "../api/execution";
import { errorMessage } from "../api/errorUtils";
import { getProject, projectKeys } from "../api/projects";
import { ErrorState, LoadingState } from "../components/Feedback";
import { ExecutionNav } from "../features/execution/ExecutionNav";
import { HealthSummary } from "../features/execution/HealthSummary";

function EvidenceReferences({ references, projectId }: { references: string[]; projectId: string }) {
  if (!references.length) return <span>No entity reference required</span>;
  return (
    <span className="evidence-references">
      {references.map((reference) =>
        reference.startsWith("TASK-") ? (
          <Link key={reference} to={`/projects/${projectId}/board#task-${reference}`}>{reference}</Link>
        ) : <span key={reference}>{reference}</span>,
      )}
    </span>
  );
}

export function ExecutionHealthPage() {
  const { projectId = "" } = useParams();
  const project = useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId),
  });
  const board = useExecutionBoard(projectId);
  if (project.isPending || board.isPending) return <LoadingState title="Calculating project health…" />;
  if (project.isError) return <ErrorState title="Project unavailable" detail="This project does not exist or is unavailable to your account." />;
  if (board.isError) return <ErrorState title="Health is not available" detail={errorMessage(board.error, "Activate a plan before calculating execution health.")} onRetry={() => void board.refetch()} />;

  const health = board.data.health;
  return (
    <div className="page-stack execution-page health-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
        <Link to={`/projects/${projectId}`}>{project.data.name}</Link><span aria-hidden="true">/</span>
        <span aria-current="page">Health</span>
      </nav>
      <header className="page-header execution-header">
        <div>
          <span className="eyebrow">Evidence-rich deterministic result</span>
          <h1>{project.data.name} health</h1>
          <p>No probability or model judgment is used. Ordered rules evaluate persisted facts for state <code>{health.state_hash.slice(0, 18)}…</code>.</p>
        </div>
        <button className="button secondary" type="button" disabled={board.isFetching} onClick={() => void board.refetch()}>
          {board.isFetching ? "Recalculating…" : "Recalculate"}
        </button>
      </header>
      <ExecutionNav projectId={projectId} />
      <HealthSummary projectId={projectId} health={health} progress={board.data.progress} />

      {health.label === "Insufficient data" ? (
        <section className="feedback-banner warning" role="status">
          <div><strong>Health needs more project data</strong><div className="feedback-copy">Set a deadline and working calendar, repair graph inconsistencies, or estimate enough active leaf tasks. The system will not invent missing values.</div></div>
        </section>
      ) : null}

      <div className="health-grid">
        <section className="detail-panel">
          <span className="eyebrow">Ordered rule result</span>
          <h2>{health.label}</h2>
          <ol className="evidence-list">
            {health.evidence.map((item, index) => (
              <li key={`${item.rule_code}-${index}`}>
                <div><strong>{item.rule_code}</strong><span className="rule-order">Rule evidence</span></div>
                <EvidenceReferences references={item.references} projectId={projectId} />
                {Object.keys(item.values).length ? (
                  <dl>{Object.entries(item.values).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{value}</dd></div>)}</dl>
                ) : <p>No numeric threshold was needed for this rule.</p>}
              </li>
            ))}
          </ol>
        </section>
        <section className="detail-panel">
          <span className="eyebrow">Schedule forecast</span>
          <h2>Current remaining-work schedule</h2>
          <dl className="health-forecast">
            <div><dt>Project finish</dt><dd>{health.project_finish ?? "Not available"}</dd></div>
            <div><dt>Buffered forecast</dt><dd>{health.forecast_finish ?? "Not available"}</dd></div>
            <div><dt>Deadline</dt><dd>{health.deadline ?? "Not set"}</dd></div>
            <div><dt>Deadline feasible</dt><dd>{health.deadline_feasible === null ? "Not evaluated" : health.deadline_feasible ? "Yes" : "No"}</dd></div>
          </dl>
          {health.blocking_path.length ? (
            <div className="blocking-path"><strong>Blocking path</strong><ol>{health.blocking_path.map((item) => <li key={item}><Link to={`/projects/${projectId}/board#task-${item}`}>{item}</Link></li>)}</ol></div>
          ) : <p>No remaining blocking path.</p>}
          {health.schedule_warnings.map((warning) => <p className="blocker-note" key={warning.code}><strong>{warning.code}</strong> {warning.detail}</p>)}
        </section>
      </div>

      <section className="detail-panel detections-panel">
        <span className="eyebrow">Monitoring conditions</span>
        <h2>Detected facts</h2>
        {health.detections.length ? (
          <ul>
            {health.detections.map((detection) => (
              <li key={detection.code} className={`detection-${detection.severity}`}>
                <div><strong>{detection.code}</strong><span>{detection.severity}</span></div>
                <EvidenceReferences references={detection.references} projectId={projectId} />
                {Object.entries(detection.values).map(([key, value]) => <small key={key}>{key.replaceAll("_", " ")}: {value}</small>)}
              </li>
            ))}
          </ul>
        ) : <p>No adverse or actionable monitoring conditions were detected.</p>}
      </section>
      <footer className="calculation-footer">
        <strong>Calculation versions</strong>
        {Object.entries(health.calculation_versions).map(([name, version]) => <span key={name}>{name}: {version}</span>)}
        <time dateTime={health.calculated_at}>Calculated {new Date(health.calculated_at).toLocaleString()}</time>
      </footer>
    </div>
  );
}
