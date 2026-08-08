export type DisplayRecord = Record<string, unknown>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const ISO_DATE_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;
const STABLE_REFERENCE = /^[A-Z][A-Z0-9_]*-\d{3,}$/;
const REFERENCE_FIELD = /(^|_)(id|key|ref|refs|reference|references|hash)$/;
const MACHINE_VALUE_FIELD = /(^|_)(code|codes|status|state|severity|priority|type|label|source)$/;

export function isDisplayRecord(value: unknown): value is DisplayRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function humanizeLabel(value: string): string {
  const label = value
    .replace(/([a-z\d])([A-Z])/g, "$1 $2")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();

  return label ? label.replace(/^\w/, (character) => character.toUpperCase()) : "Value";
}

function formatDate(value: string, includesTime: boolean): string {
  const date = includesTime ? new Date(value) : new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat("en", includesTime
    ? {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZone: "UTC",
        timeZoneName: "short",
      }
    : { dateStyle: "medium", timeZone: "UTC" }).format(date);
}

export function displayScalar(value: unknown, fieldName?: string): string {
  if (value === null || value === undefined || value === "") return "Not recorded";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return Number.isFinite(value) ? value.toLocaleString("en") : "Not recorded";
  if (typeof value === "bigint") return value.toLocaleString("en");
  if (typeof value !== "string") return "Not available";

  const trimmed = value.trim();
  if (!trimmed) return "Not recorded";
  if (ISO_DATE.test(trimmed)) return formatDate(trimmed, false);
  if (ISO_DATE_TIME.test(trimmed)) return formatDate(trimmed, true);

  const normalizedField = fieldName?.toLowerCase() ?? "";
  if (
    MACHINE_VALUE_FIELD.test(normalizedField)
    && !REFERENCE_FIELD.test(normalizedField)
    && !STABLE_REFERENCE.test(trimmed)
    && /^[A-Za-z][A-Za-z0-9_-]*$/.test(trimmed)
  ) {
    return humanizeLabel(trimmed);
  }
  return value;
}

export function evidenceReferenceLabel(reference: string): string {
  const eventMatch = /^EVENT-([0-9a-f]{8})[0-9a-f-]+$/i.exec(reference);
  if (eventMatch) return `Event ${eventMatch[1].toUpperCase()}`;

  if (reference.startsWith("DETECTION-")) {
    return `${humanizeLabel(reference.slice("DETECTION-".length))} detection`;
  }
  return reference;
}

export function cleanNarrativeText(value: string): string {
  return value
    .replace(/<\/?(?:UNTRUSTED|TRUSTED)_[A-Z][A-Z0-9_:-]*(?:\s[^>]*)?>/gi, "")
    .replace(/^(?:BEGIN|END)_(?:UNTRUSTED|TRUSTED)_[A-Z0-9_:-]+\s*$/gim, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
