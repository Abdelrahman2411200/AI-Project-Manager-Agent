import type { EvidenceFact } from "../../api/types";
import { StructuredValue } from "../../components/StructuredValue";
import {
  displayScalar,
  evidenceReferenceLabel,
  humanizeLabel,
  isDisplayRecord,
} from "../../utils/display";

function taskTitle(fact: EvidenceFact): string {
  return isDisplayRecord(fact.value) && typeof fact.value.title === "string"
    ? fact.value.title
    : humanizeLabel(fact.fact_key);
}

function taskStatus(fact: EvidenceFact): string | null {
  return isDisplayRecord(fact.value) && typeof fact.value.status === "string"
    ? fact.value.status
    : null;
}

interface TaskSchedule {
  start?: unknown;
  finish?: unknown;
}

function taskScheduleIndex(evidence: Record<string, EvidenceFact>): Record<string, TaskSchedule> {
  const result: Record<string, TaskSchedule> = {};
  for (const fact of Object.values(evidence)) {
    if (fact.entity_type !== "forecast" || !isDisplayRecord(fact.value) || !isDisplayRecord(fact.value.tasks)) continue;
    for (const item of Object.values(fact.value.tasks)) {
      if (!isDisplayRecord(item) || typeof item.stable_key !== "string") continue;
      result[item.stable_key] = { start: item.start_date, finish: item.finish_date };
    }
  }
  return result;
}

function TaskEvidenceDetails({ fact, schedule }: { fact: EvidenceFact; schedule?: TaskSchedule }) {
  if (!isDisplayRecord(fact.value)) return <StructuredValue value={fact.value} />;
  const value = fact.value;
  const scheduleStart = value.planned_start ?? value.start_date ?? schedule?.start;
  const scheduleFinish = value.planned_finish ?? value.finish_date ?? schedule?.finish;
  const scheduleDisplay = scheduleStart || scheduleFinish
    ? [displayScalar(scheduleStart), displayScalar(scheduleFinish)].join(" to ")
    : null;
  const fields = [
    ["Priority", value.priority ?? value.priority_label],
    ["Progress", value.progress ?? value.progress_display],
    ["Estimated effort", value.estimated_hours ? `${displayScalar(value.estimated_hours)} hours` : null],
    ["Schedule", scheduleDisplay],
    ["Blocked reason", value.blocked_reason ?? value.reason],
  ].filter((field): field is [string, unknown] => field[1] !== null && field[1] !== undefined && field[1] !== "");
  if (!fields.length) return null;
  return (
    <dl className="task-evidence-facts">
      {fields.map(([label, item]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd><StructuredValue value={item} fieldName={label} /></dd>
        </div>
      ))}
    </dl>
  );
}

export function ReportEvidenceIndex({ evidence }: { evidence: Record<string, EvidenceFact> }) {
  const entries = Object.entries(evidence).sort(([left], [right]) =>
    left.localeCompare(right, undefined, { numeric: true }),
  );
  const tasks = entries.filter(([, fact]) => fact.entity_type === "task");
  const evidenceOrder: Record<string, number> = {
    period: 0,
    metric: 1,
    forecast: 2,
    milestone: 3,
    risk: 4,
    event: 5,
    dependency: 6,
    detection: 7,
    project: 8,
  };
  const claims = entries
    .filter(([, fact]) => fact.entity_type !== "task")
    .sort(([leftRef, left], [rightRef, right]) =>
      (evidenceOrder[left.entity_type] ?? 99) - (evidenceOrder[right.entity_type] ?? 99)
      || leftRef.localeCompare(rightRef, undefined, { numeric: true }),
    );
  const schedules = taskScheduleIndex(evidence);

  return (
    <>
      {tasks.length ? (
        <section className="detail-panel report-task-section" aria-labelledby="report-task-index-title">
          <span className="eyebrow">Referenced work</span>
          <h2 id="report-task-index-title">Task index</h2>
          <p className="section-description">Current task facts cited by this immutable report.</p>
          <ol className="report-task-index">
            {tasks.map(([reference, fact]) => {
              const status = taskStatus(fact);
              return (
                <li key={reference}>
                  <header>
                    <code>{reference}</code>
                    {status ? <span className={`task-evidence-status status-${status}`}>{humanizeLabel(status)}</span> : null}
                  </header>
                  <h3>{taskTitle(fact)}</h3>
                  <TaskEvidenceDetails fact={fact} schedule={schedules[reference]} />
                </li>
              );
            })}
          </ol>
        </section>
      ) : null}

      <section className="detail-panel report-evidence-section" aria-labelledby="report-evidence-index-title">
        <span className="eyebrow">Claim verification</span>
        <h2 id="report-evidence-index-title">Evidence index</h2>
        <p className="section-description">Each reference identifies a persisted fact used to verify statements in this report.</p>
        {claims.length ? (
          <ol className="report-evidence-index">
            {claims.map(([reference, fact]) => (
              <li key={reference}>
                <header className="report-evidence-header">
                  <div>
                    <code title={reference}>{evidenceReferenceLabel(reference)}</code>
                    <h3>{humanizeLabel(fact.fact_key)}</h3>
                  </div>
                  <span>{humanizeLabel(fact.entity_type)}</span>
                </header>
                <StructuredValue value={fact.value} />
              </li>
            ))}
          </ol>
        ) : <p className="evidence-empty-value">No additional claim evidence was recorded.</p>}
      </section>
    </>
  );
}
