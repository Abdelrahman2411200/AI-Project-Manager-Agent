import type { EvidenceFact } from "../../api/types";

type EvidenceRecord = Record<string, unknown>;

function isRecord(value: unknown): value is EvidenceRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function textValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not recorded";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" || typeof value === "number" || typeof value === "bigint") {
    return String(value);
  }
  return "Unsupported value";
}

function evidenceLabel(value: string): string {
  return value
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function recordTitle(key: string, value: EvidenceRecord): string {
  for (const candidate of ["stable_key", "task_ref", "reference", "code", "title", "name"]) {
    const candidateValue = value[candidate];
    if (typeof candidateValue === "string" && candidateValue) {
      return candidateValue;
    }
  }
  return evidenceLabel(key);
}

function recordTitleKey(value: EvidenceRecord): string | null {
  return ["stable_key", "task_ref", "reference", "code", "title", "name"].find(
    (candidate) => typeof value[candidate] === "string" && value[candidate],
  ) ?? null;
}

function isRecordCollection(value: EvidenceRecord): boolean {
  const entries = Object.values(value);
  return entries.length > 0 && entries.every(isRecord);
}

export function EvidenceValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    const items: unknown[] = value;
    if (!items.length) return <span className="evidence-empty-value">None recorded</span>;
    const scalarItems = items.every((item) => !Array.isArray(item) && !isRecord(item));
    if (scalarItems) {
      return (
        <ul className="evidence-compact-values">
          {items.map((item, index) => <li key={`${index}-${textValue(item)}`}>{textValue(item)}</li>)}
        </ul>
      );
    }
    return (
      <ol className="evidence-value-list">
        {items.map((item, index) => (
          <li key={isRecord(item) ? recordTitle(String(index + 1), item) : `${index}-${textValue(item)}`}>
            <EvidenceValue value={item} />
          </li>
        ))}
      </ol>
    );
  }

  if (isRecord(value)) {
    const entries = Object.entries(value);
    if (!entries.length) return <span className="evidence-empty-value">None recorded</span>;
    if (isRecordCollection(value)) {
      return (
        <div className="evidence-record-grid">
          {entries
            .sort(([, left], [, right]) =>
              recordTitle("", left as EvidenceRecord).localeCompare(
                recordTitle("", right as EvidenceRecord),
                undefined,
                { numeric: true },
              ),
            )
            .map(([key, item]) => (
              <section className="evidence-record" key={key}>
                <h4>{recordTitle(key, item as EvidenceRecord)}</h4>
                <EvidenceValue
                  value={Object.fromEntries(
                    Object.entries(item as EvidenceRecord).filter(
                      ([field]) => field !== recordTitleKey(item as EvidenceRecord),
                    ),
                  )}
                />
              </section>
            ))}
        </div>
      );
    }
    return (
      <dl className="evidence-field-list">
        {entries.map(([key, item]) => (
          <div key={key}>
            <dt>{evidenceLabel(key)}</dt>
            <dd><EvidenceValue value={item} /></dd>
          </div>
        ))}
      </dl>
    );
  }

  return <span>{textValue(value)}</span>;
}

function taskTitle(fact: EvidenceFact): string {
  return isRecord(fact.value) && typeof fact.value.title === "string"
    ? fact.value.title
    : evidenceLabel(fact.fact_key);
}

function taskStatus(fact: EvidenceFact): string | null {
  return isRecord(fact.value) && typeof fact.value.status === "string"
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
    if (fact.entity_type !== "forecast" || !isRecord(fact.value) || !isRecord(fact.value.tasks)) continue;
    for (const item of Object.values(fact.value.tasks)) {
      if (!isRecord(item) || typeof item.stable_key !== "string") continue;
      result[item.stable_key] = { start: item.start_date, finish: item.finish_date };
    }
  }
  return result;
}

function TaskEvidenceDetails({ fact, schedule }: { fact: EvidenceFact; schedule?: TaskSchedule }) {
  if (!isRecord(fact.value)) return <EvidenceValue value={fact.value} />;
  const value = fact.value;
  const scheduleStart = value.planned_start ?? value.start_date ?? schedule?.start;
  const scheduleFinish = value.planned_finish ?? value.finish_date ?? schedule?.finish;
  const scheduleDisplay = scheduleStart || scheduleFinish
    ? [textValue(scheduleStart), textValue(scheduleFinish)].join(" to ")
    : null;
  const fields = [
    ["Priority", value.priority ?? value.priority_label],
    ["Progress", value.progress ?? value.progress_display],
    ["Estimated effort", value.estimated_hours ? `${textValue(value.estimated_hours)} hours` : null],
    ["Schedule", scheduleDisplay],
    ["Blocked reason", value.blocked_reason ?? value.reason],
  ].filter((field): field is [string, unknown] => field[1] !== null && field[1] !== undefined && field[1] !== "");
  if (!fields.length) return null;
  return (
    <dl className="task-evidence-facts">
      {fields.map(([label, item]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd><EvidenceValue value={item} /></dd>
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
                    {status ? <span className={`task-evidence-status status-${status}`}>{evidenceLabel(status)}</span> : null}
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
                    <code>{reference}</code>
                    <h3>{evidenceLabel(fact.fact_key)}</h3>
                  </div>
                  <span>{evidenceLabel(fact.entity_type)}</span>
                </header>
                <EvidenceValue value={fact.value} />
              </li>
            ))}
          </ol>
        ) : <p className="evidence-empty-value">No additional claim evidence was recorded.</p>}
      </section>
    </>
  );
}
