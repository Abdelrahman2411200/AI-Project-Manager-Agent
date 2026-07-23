import { Link } from "react-router-dom";

import type { ProjectHealthView, ProjectProgressView } from "../../api/types";

function percent(value: string | null): string {
  return value === null ? "Not available" : `${Math.round(Number(value) * 100)}%`;
}

export function HealthSummary({
  projectId,
  health,
  progress,
}: {
  projectId: string;
  health: ProjectHealthView;
  progress: ProjectProgressView;
}) {
  const icon =
    health.label === "Completed"
      ? "✓"
      : health.label === "On track"
        ? "↗"
        : health.label === "Insufficient data"
          ? "?"
          : "!";
  return (
    <section className="execution-summary" aria-label="Execution summary">
      <article className={`health-summary-card health-${health.label.toLowerCase().replaceAll(" ", "-")}`}>
        <span className="health-icon" aria-hidden="true">{icon}</span>
        <div>
          <span>Project health</span>
          <strong>{health.label}</strong>
          <small>{health.rule_codes.join(" · ")}</small>
        </div>
        <Link to={`/projects/${projectId}/health`}>View evidence</Link>
      </article>
      <article>
        <span>Weighted progress</span>
        <strong>{percent(progress.project.fraction)}</strong>
        <progress
          max={1}
          value={Number(progress.project.fraction ?? 0)}
          aria-label={`Weighted project progress ${percent(progress.project.fraction)}`}
        />
        <small>
          {progress.project.weighted_completed_hours} of {progress.project.estimated_hours} weighted hours
        </small>
      </article>
      <article>
        <span>Forecast finish</span>
        <strong>{health.forecast_finish ?? "Not available"}</strong>
        <small>Deadline {health.deadline ?? "not set"}</small>
      </article>
    </section>
  );
}
