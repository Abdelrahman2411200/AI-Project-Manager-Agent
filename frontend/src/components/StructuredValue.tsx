import {
  displayScalar,
  humanizeLabel,
  isDisplayRecord,
  type DisplayRecord,
} from "../utils/display";

function recordTitle(key: string, value: DisplayRecord): string {
  for (const candidate of ["stable_key", "task_ref", "reference", "code", "title", "name"]) {
    const candidateValue = value[candidate];
    if (typeof candidateValue === "string" && candidateValue) {
      return displayScalar(candidateValue, candidate);
    }
  }
  return humanizeLabel(key);
}

function recordTitleKey(value: DisplayRecord): string | null {
  return ["stable_key", "task_ref", "reference", "code", "title", "name"].find(
    (candidate) => typeof value[candidate] === "string" && value[candidate],
  ) ?? null;
}

function isRecordCollection(value: DisplayRecord): boolean {
  const entries = Object.values(value);
  return entries.length > 0 && entries.every(isDisplayRecord);
}

interface StructuredValueProps {
  value: unknown;
  fieldName?: string;
  emptyLabel?: string;
}

export function StructuredValue({ value, fieldName, emptyLabel = "None recorded" }: StructuredValueProps) {
  if (Array.isArray(value)) {
    const items: unknown[] = value;
    if (!items.length) return <span className="structured-empty-value">{emptyLabel}</span>;
    const scalarItems = items.every((item) => !Array.isArray(item) && !isDisplayRecord(item));
    if (scalarItems) {
      return (
        <ul className="structured-compact-values">
          {items.map((item, index) => (
            <li key={`${index}-${displayScalar(item, fieldName)}`}>{displayScalar(item, fieldName)}</li>
          ))}
        </ul>
      );
    }
    return (
      <ol className="structured-value-list">
        {items.map((item, index) => (
          <li key={isDisplayRecord(item) ? recordTitle(String(index + 1), item) : String(index)}>
            <StructuredValue value={item} fieldName={fieldName} emptyLabel={emptyLabel} />
          </li>
        ))}
      </ol>
    );
  }

  if (isDisplayRecord(value)) {
    const entries = Object.entries(value);
    if (!entries.length) return <span className="structured-empty-value">{emptyLabel}</span>;
    if (isRecordCollection(value)) {
      return (
        <div className="structured-record-grid">
          {entries
            .sort(([, left], [, right]) =>
              recordTitle("", left as DisplayRecord).localeCompare(
                recordTitle("", right as DisplayRecord),
                undefined,
                { numeric: true },
              ),
            )
            .map(([key, item]) => {
              const record = item as DisplayRecord;
              const titleKey = recordTitleKey(record);
              return (
                <section className="structured-record" key={key}>
                  <h4>{recordTitle(key, record)}</h4>
                  <StructuredValue
                    value={Object.fromEntries(Object.entries(record).filter(([candidate]) => candidate !== titleKey))}
                    emptyLabel={emptyLabel}
                  />
                </section>
              );
            })}
        </div>
      );
    }
    return (
      <dl className="structured-field-list">
        {entries.map(([key, item]) => (
          <div key={key}>
            <dt>{humanizeLabel(key)}</dt>
            <dd><StructuredValue value={item} fieldName={key} emptyLabel={emptyLabel} /></dd>
          </div>
        ))}
      </dl>
    );
  }

  return <span>{displayScalar(value, fieldName)}</span>;
}
