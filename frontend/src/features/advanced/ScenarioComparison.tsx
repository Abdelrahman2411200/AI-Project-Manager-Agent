import type { ScenarioView } from "../../api/types";
import { displayScalar } from "../../utils/display";

const METRICS = [
  ["Total effort", "total_effort_hours", "hours"],
  ["Weekly capacity", "capacity_hours_per_week", "hours/week"],
  ["Forecast weeks", "forecast_weeks", "weeks"],
  ["Critical path", "critical_path_hours", "hours"],
] as const;

function numberValue(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function direction(baseline: unknown, scenario: unknown): string {
  const before = numberValue(baseline);
  const after = numberValue(scenario);
  if (before === null || after === null || before === after) return "unchanged";
  return after > before ? "increased" : "decreased";
}

export function ScenarioComparison({ scenario }: { scenario: ScenarioView }) {
  const baseline = scenario.result_json.baseline;
  const result = scenario.result_json.scenario;

  return (
    <section className="advanced-section scenario-comparison" aria-labelledby="scenario-comparison-heading">
      <div className="advanced-section-heading">
        <div>
          <span className="eyebrow">Immutable virtual clone</span>
          <h2 id="scenario-comparison-heading">Baseline and scenario comparison</h2>
          <p>
            Bar length is supplemental. Values and explicit change direction are repeated
            in the table.
          </p>
        </div>
        <span className="metric-pill">Calculation {scenario.calculation_version}</span>
      </div>

      <div className="scenario-bars" aria-label="Visual comparison of baseline and scenario metrics">
        {METRICS.map(([label, key, unit]) => {
          const before = numberValue(baseline[key]) ?? 0;
          const after = numberValue(result[key]) ?? 0;
          const maximum = Math.max(before, after, 1);
          return (
            <div className="scenario-bar-group" key={key}>
              <div>
                <strong>{label}</strong>
                <span>{direction(before, after)}</span>
              </div>
              <div className="scenario-bar-row">
                <span>Baseline</span>
                <i style={{ width: `${Math.max((before / maximum) * 100, 2)}%` }} />
                <b>{displayScalar(baseline[key], key)} {unit}</b>
              </div>
              <div className="scenario-bar-row scenario">
                <span>Scenario</span>
                <i style={{ width: `${Math.max((after / maximum) * 100, 2)}%` }} />
                <b>{displayScalar(result[key], key)} {unit}</b>
              </div>
            </div>
          );
        })}
      </div>

      <div className="table-scroll" tabIndex={0}>
        <table>
          <caption>Exact baseline and virtual scenario values</caption>
          <thead>
            <tr>
              <th>Metric</th>
              <th>Baseline</th>
              <th>Scenario</th>
              <th>Direction</th>
            </tr>
          </thead>
          <tbody>
            {[
              ...METRICS.map(([label, key]) => [label, key] as const),
              ["Forecast finish", "forecast_finish"] as const,
              ["Deadline delta days", "deadline_delta_days"] as const,
            ].map(([label, key]) => (
              <tr key={key}>
                <th scope="row">{label}</th>
                <td>{displayScalar(baseline[key], key)}</td>
                <td>{displayScalar(result[key], key)}</td>
                <td>{direction(baseline[key], result[key])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <dl className="scenario-deltas">
        <div>
          <dt>Forecast finish delta</dt>
          <dd>{scenario.result_json.delta.forecast_finish_days} days</dd>
        </div>
        <div>
          <dt>Effort delta</dt>
          <dd>{scenario.result_json.delta.effort_hours} hours</dd>
        </div>
        <div>
          <dt>Critical-path delta</dt>
          <dd>{scenario.result_json.delta.critical_path_hours} hours</dd>
        </div>
      </dl>
    </section>
  );
}
