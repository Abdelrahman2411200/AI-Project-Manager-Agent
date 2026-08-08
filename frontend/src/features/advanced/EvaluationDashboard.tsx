import { useQuery } from "@tanstack/react-query";

import { advancedKeys, getLatestEvaluation } from "../../api/advanced";
import { errorMessage } from "../../api/errorUtils";
import { ErrorState, LoadingState, StateBadge } from "../../components/Feedback";
import { displayScalar, humanizeLabel } from "../../utils/display";

function metricLabel(value: string): string {
  return humanizeLabel(value);
}

function metricValue(key: string, value: number): string {
  if (key.includes("rate") || key.includes("coverage") || key.includes("compliance") || key.includes("validity")) {
    return `${(value * 100).toFixed(1)}%`;
  }
  return String(value);
}

export function EvaluationDashboard() {
  const evaluation = useQuery({
    queryKey: advancedKeys.evaluation(),
    queryFn: getLatestEvaluation,
  });

  if (evaluation.isPending) {
    return <LoadingState title="Loading evaluation evidence…" detail="Verifying the reviewed university baseline." />;
  }
  if (evaluation.isError) {
    return (
      <ErrorState
        title="Evaluation dashboard unavailable"
        detail={errorMessage(evaluation.error, "The reviewed baseline could not be verified.")}
        onRetry={() => void evaluation.refetch()}
      />
    );
  }

  const data = evaluation.data;
  return (
    <section className="advanced-section evaluation-dashboard" aria-labelledby="evaluation-heading">
      <div className="advanced-section-heading">
        <div>
          <span className="eyebrow">Reviewed release evidence</span>
          <h2 id="evaluation-heading">Evaluation dashboard</h2>
          <p>
            Scores come from the versioned deterministic fixture runner. This view does not
            trigger a provider call or alter the accepted baseline.
          </p>
        </div>
        <StateBadge state={data.release_status} />
      </div>

      <dl className="evaluation-summary">
        <div>
          <dt>Fixtures passing</dt>
          <dd>{data.pass_count} / {data.fixture_count}</dd>
        </div>
        {Object.entries(data.summary).map(([key, value]) => (
          <div key={key}>
            <dt>{metricLabel(key)}</dt>
            <dd>{metricValue(key, value)}</dd>
          </div>
        ))}
      </dl>

      <div className="table-scroll" tabIndex={0}>
        <table>
          <caption>Evaluation result by required university fixture</caption>
          <thead>
            <tr>
              <th>Fixture</th>
              <th>Module coverage</th>
              <th>Missing tasks</th>
              <th>Task sizing</th>
              <th>Dependencies</th>
              <th>Hallucinations</th>
              <th>Schedule oracle</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {data.fixtures.map((fixture) => (
              <tr key={fixture.fixture_id}>
                <th scope="row">{metricLabel(fixture.fixture_id)}</th>
                <td>{metricValue("module_coverage", Number(fixture.metrics.module_coverage))}</td>
                <td>{metricValue("missing_task_rate", Number(fixture.metrics.missing_task_rate))}</td>
                <td>{metricValue("task_size_compliance", Number(fixture.metrics.task_size_compliance))}</td>
                <td>{metricValue("dependency_validity", Number(fixture.metrics.dependency_validity))}</td>
                <td>{metricValue("hallucination_rate", Number(fixture.metrics.hallucination_rate))}</td>
                <td>{fixture.metrics.schedule_match === true ? "Matched" : "Mismatch"}</td>
                <td>{fixture.passed ? "Passed" : "Failed"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <details>
        <summary>Release thresholds and provenance</summary>
        <dl className="threshold-list">
          {Object.entries(data.thresholds).map(([metric, threshold]) => (
            <div key={metric}>
              <dt>{metricLabel(metric)}</dt>
              <dd>{displayScalar(threshold, metric)}</dd>
            </div>
          ))}
        </dl>
        <p>
          Dataset <code>{data.dataset_version}</code> · <code>{data.dataset_hash}</code>
        </p>
        <p>Fixture source: <code>{data.fixture_source}</code></p>
      </details>
    </section>
  );
}
