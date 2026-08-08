import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { downloadReport, getReport, insightKeys } from "../api/insights";
import { errorMessage } from "../api/errorUtils";
import { ErrorState, FeedbackBanner, LoadingState, StateBadge } from "../components/Feedback";
import { StructuredValue } from "../components/StructuredValue";
import { ReportEvidenceIndex } from "../features/insights/ReportEvidenceIndex";
import { cleanNarrativeText, evidenceReferenceLabel, humanizeLabel } from "../utils/display";

interface CitedStatement {
  text: string;
  evidence_refs: string[];
}

function citedList(value: unknown): CitedStatement[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is CitedStatement =>
      typeof item === "object" &&
      item !== null &&
      typeof (item as CitedStatement).text === "string" &&
      Array.isArray((item as CitedStatement).evidence_refs),
  );
}

function CitedItems({ title, items }: { title: string; items: CitedStatement[] }) {
  if (!items.length) return null;
  return (
    <section>
      <h2>{title}</h2>
      <ul className="cited-statement-list">
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>
            <p>{cleanNarrativeText(item.text)}</p>
            <span>{item.evidence_refs.map((reference) => <code key={reference} title={reference}>{evidenceReferenceLabel(reference)}</code>)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ReportDetailPage() {
  const { reportId = "" } = useParams();
  const [downloadError, setDownloadError] = useState<unknown>(null);
  const [downloading, setDownloading] = useState<"md" | "pdf" | null>(null);
  const report = useQuery({
    queryKey: insightKeys.report(reportId),
    queryFn: () => getReport(reportId),
    enabled: Boolean(reportId),
  });
  if (report.isPending) return <LoadingState title="Opening factual report…" />;
  if (report.isError) return <ErrorState title="Report unavailable" detail={errorMessage(report.error, "This report does not exist or is unavailable to your account.")} />;

  const narrative = report.data.narrative ?? {};
  const progress = narrative.progress_statement as CitedStatement | undefined;
  const caveats = Array.isArray(narrative.caveats)
    ? narrative.caveats
        .filter((item): item is string => typeof item === "string")
        .map(cleanNarrativeText)
        .filter(Boolean)
    : [];
  const narrativeTitle = typeof narrative.title === "string"
    ? cleanNarrativeText(narrative.title)
    : "";
  const periodSummary = typeof narrative.period_summary === "string"
    ? cleanNarrativeText(narrative.period_summary)
    : "";

  return (
    <div className="page-stack report-detail-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
        <Link to={`/projects/${report.data.project_id}/reports`}>Reports</Link><span aria-hidden="true">/</span>
        <span aria-current="page">{report.data.report_type} report</span>
      </nav>
      <header className="page-header report-detail-header">
        <div>
          <span className="eyebrow">Immutable report · version {report.data.data.version_number}</span>
          <h1>{narrativeTitle || `${report.data.data.project_name} factual report`}</h1>
          <p>{report.data.period_start} to {report.data.period_end} · {report.data.data.health_label}</p>
        </div>
        <div className="header-actions">
          <StateBadge state={report.data.status} />
          <div className="button-row">
            <button
              className="button secondary"
              type="button"
              disabled={downloading !== null}
              onClick={() => {
                setDownloading("md");
                setDownloadError(null);
                void downloadReport(reportId, "md")
                  .catch(setDownloadError)
                  .finally(() => setDownloading(null));
              }}
            >
              {downloading === "md" ? "Preparing…" : "Download Markdown"}
            </button>
            <button
              className="button primary"
              type="button"
              disabled={downloading !== null}
              onClick={() => {
                setDownloading("pdf");
                setDownloadError(null);
                void downloadReport(reportId, "pdf")
                  .catch(setDownloadError)
                  .finally(() => setDownloading(null));
              }}
            >
              {downloading === "pdf" ? "Rendering…" : "Download PDF"}
            </button>
          </div>
        </div>
      </header>
      {report.data.status === "partial" ? (
        <FeedbackBanner tone="warning" title="Factual fallback used">
          <p>The narrative was unavailable or rejected ({report.data.narrative_failure_code ?? "unknown reason"}). The stored data and Markdown remain deterministic.</p>
        </FeedbackBanner>
      ) : null}
      {downloadError ? (
        <FeedbackBanner tone="danger" title="Download failed">
          <p>{errorMessage(downloadError, "Try downloading the report again.")}</p>
        </FeedbackBanner>
      ) : null}

      <article className="report-document">
        {periodSummary ? <p className="report-lede">{periodSummary}</p> : <p className="report-lede">This report uses the deterministic factual snapshot shown below.</p>}
        {progress ? <CitedItems title="Progress" items={[progress]} /> : null}
        <CitedItems title="Completed work" items={citedList(narrative.completed_items)} />
        <CitedItems title="Blockers" items={citedList(narrative.blockers)} />
        <CitedItems title="Risks" items={citedList(narrative.risks)} />
        <CitedItems title="Next actions" items={citedList(narrative.next_actions)} />
        <CitedItems title="Decisions needed" items={citedList(narrative.decisions_needed)} />
        {caveats.length ? <section><h2>Caveats</h2><ul>{caveats.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
      </article>

      <section className="report-facts detail-panel">
        <span className="eyebrow">Stored ReportData</span>
        <h2>Factual snapshot</h2>
        <dl>
          {Object.entries(report.data.data.metrics).map(([key, value]) => (
            <div key={key}><dt>{humanizeLabel(key)}</dt><dd><StructuredValue value={value} fieldName={key} /></dd></div>
          ))}
        </dl>
      </section>
      <ReportEvidenceIndex evidence={report.data.data.evidence} />
      <footer className="calculation-footer">
        <strong>Content hash</strong><code>{report.data.content_hash}</code>
        <span>State {report.data.data.state_hash}</span>
      </footer>
    </div>
  );
}
