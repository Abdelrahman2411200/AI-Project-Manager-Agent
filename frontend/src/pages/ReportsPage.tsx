import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  insightKeys,
  listReports,
  startReport,
} from "../api/insights";
import { errorMessage } from "../api/errorUtils";
import { getProject, projectKeys } from "../api/projects";
import { getAgentRun, planningRunPollInterval, runKeys } from "../api/runs";
import type { ReportType } from "../api/types";
import { ErrorState, FeedbackBanner, LoadingState, StateBadge } from "../components/Feedback";
import { ExecutionNav } from "../features/execution/ExecutionNav";

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function ReportsPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const defaults = useMemo(() => {
    const end = new Date();
    const start = new Date(end);
    start.setUTCDate(end.getUTCDate() - 6);
    return { start: isoDate(start), end: isoDate(end) };
  }, []);
  const [reportType, setReportType] = useState<ReportType>("weekly");
  const [periodStart, setPeriodStart] = useState(defaults.start);
  const [periodEnd, setPeriodEnd] = useState(defaults.end);
  const [runId, setRunId] = useState("");
  const project = useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId),
  });
  const reports = useQuery({
    queryKey: insightKeys.reports(projectId),
    queryFn: () => listReports(projectId),
    enabled: Boolean(projectId),
  });
  const run = useQuery({
    queryKey: runKeys.detail(runId),
    queryFn: () => getAgentRun(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => planningRunPollInterval(query.state.data),
  });
  const create = useMutation({
    mutationFn: () => startReport(projectId, reportType, periodStart, periodEnd),
    onSuccess: (result) => setRunId(result.run_id),
  });

  useEffect(() => {
    const reportId =
      typeof run.data?.outcome?.report_id === "string"
        ? run.data.outcome.report_id
        : null;
    if (reportId && (run.data?.status === "completed" || run.data?.status === "partial")) {
      void queryClient.invalidateQueries({ queryKey: insightKeys.reports(projectId) });
      void navigate(`/reports/${reportId}`);
    }
  }, [navigate, projectId, queryClient, run.data]);

  if (project.isPending || reports.isPending) return <LoadingState title="Loading factual reports…" />;
  if (project.isError) return <ErrorState title="Project unavailable" detail="This project does not exist or is unavailable to your account." />;
  if (reports.isError) return <ErrorState title="Reports are unavailable" detail={errorMessage(reports.error, "Activate a plan before generating reports.")} onRetry={() => void reports.refetch()} />;

  return (
    <div className="page-stack execution-page reports-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
        <Link to={`/projects/${projectId}`}>{project.data.name}</Link><span aria-hidden="true">/</span>
        <span aria-current="page">Reports</span>
      </nav>
      <header className="page-header execution-header">
        <div>
          <span className="eyebrow">Persisted facts · cited narrative</span>
          <h1>{project.data.name} reports</h1>
          <p>Generate immutable reports from the approved plan, monitoring snapshots, and execution events.</p>
        </div>
      </header>
      <ExecutionNav projectId={projectId} />

      <section className="report-generator detail-panel" aria-labelledby="report-generator-heading">
        <div>
          <span className="eyebrow">On demand</span>
          <h2 id="report-generator-heading">Generate a factual report</h2>
          <p>The data snapshot is captured immediately. AI wording is optional and every factual statement must cite stored evidence.</p>
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <label>
            Report focus
            <select value={reportType} onChange={(event) => setReportType(event.target.value as ReportType)}>
              <option value="weekly">Weekly status</option>
              <option value="project">Project status</option>
              <option value="milestone">Milestones</option>
              <option value="risk">Risks</option>
              <option value="comparison">Period comparison</option>
            </select>
          </label>
          <label>
            Period start
            <input type="date" required value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} />
          </label>
          <label>
            Period end
            <input type="date" required min={periodStart} value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} />
          </label>
          <button className="button primary" type="submit" disabled={create.isPending || Boolean(runId && !run.data?.completed_at)}>
            {create.isPending || (runId && !run.data?.completed_at) ? "Generating…" : "Generate report"}
          </button>
        </form>
        {create.isError || run.isError ? (
          <FeedbackBanner tone="danger" title="Report could not be generated">
            <p>{errorMessage(create.error ?? run.error, "Check the report period and try again.")}</p>
          </FeedbackBanner>
        ) : null}
        {runId && run.data && !run.data.completed_at ? (
          <div className="report-run-status" role="status" aria-live="polite">
            <span className="loading-spinner" aria-hidden="true" />
            <div><strong>Building the report</strong><span>{run.data.current_step.replaceAll("_", " ")}</span></div>
          </div>
        ) : null}
      </section>

      <section aria-labelledby="report-history-heading">
        <div className="section-heading split">
          <div><span className="eyebrow">Immutable history</span><h2 id="report-history-heading">Generated reports</h2></div>
          <span>{reports.data.length} report{reports.data.length === 1 ? "" : "s"}</span>
        </div>
        {reports.data.length ? (
          <ul className="report-list">
            {reports.data.map((report) => (
              <li key={report.id}>
                <div>
                  <span className="task-key">{report.report_type.toUpperCase()}</span>
                  <h3><Link to={`/reports/${report.id}`}>{report.period_start} to {report.period_end}</Link></h3>
                  <time dateTime={report.created_at}>Generated {new Date(report.created_at).toLocaleString()}</time>
                </div>
                <div><StateBadge state={report.status} /><code>{report.content_hash.slice(0, 18)}…</code></div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="empty-inline"><strong>No reports yet</strong><p>Generate the first report for a selected factual period.</p></div>
        )}
      </section>
    </div>
  );
}
