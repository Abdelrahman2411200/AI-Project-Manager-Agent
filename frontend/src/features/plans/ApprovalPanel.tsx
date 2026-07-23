import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import {
  approvePlanVersion,
  requestPlanChanges,
  submitPlanReview,
  validatePlanVersion,
} from "../../api/plans";
import type { PlanGraphView, PlanValidationView } from "../../api/types";
import { errorMessage, isConflict } from "../../api/errorUtils";
import { FeedbackBanner, StateBadge } from "../../components/Feedback";

interface ApprovalPanelProps {
  plan: PlanGraphView;
  onUpdated: () => Promise<void>;
}

function ReferenceLinks({ references }: { references: string[] }) {
  if (!references.length) return null;
  return (
    <span className="issue-references">
      {references.map((reference) => (
        <a key={reference} href={`#entity-${reference}`}>{reference}</a>
      ))}
    </span>
  );
}

export function ApprovalPanel({ plan, onUpdated }: ApprovalPanelProps) {
  const [validation, setValidation] = useState<PlanValidationView | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [approvalReason, setApprovalReason] = useState("");
  const [changeReason, setChangeReason] = useState("");
  const validate = useMutation({
    mutationFn: () => validatePlanVersion(plan.id, plan.row_version),
    onSuccess: async (result) => {
      setValidation(result);
      await onUpdated();
    },
  });
  const submitReview = useMutation({
    mutationFn: () => submitPlanReview(plan.id, plan.row_version),
    onSuccess: onUpdated,
  });
  const requestChanges = useMutation({
    mutationFn: () => requestPlanChanges(plan.id, plan.row_version, changeReason),
    onSuccess: async () => {
      setChangeReason("");
      await onUpdated();
    },
  });
  const approve = useMutation({
    mutationFn: () =>
      approvePlanVersion(
        plan.id,
        plan.row_version,
        plan.content_hash,
        approvalReason.trim() || undefined,
      ),
    onSuccess: async () => {
      setConfirming(false);
      setConfirmed(false);
      await onUpdated();
    },
  });
  const mutations = [validate, submitReview, requestChanges, approve];
  const activeMutation = mutations.find((mutation) => mutation.isPending);
  const mutationError = mutations.find((mutation) => mutation.isError)?.error;
  const conflict = isConflict(mutationError);
  const issues = validation?.issues ?? [];

  return (
    <aside className="approval-panel" aria-labelledby="approval-title">
      <div className="approval-header">
        <div><span className="eyebrow">Owner decision</span><h2 id="approval-title">Validation and approval</h2></div>
        <StateBadge state={plan.state} />
      </div>
      <p className="approval-intro">
        Deterministic rules calculate dates, priority, graph validity, and quality. Approval
        activates only the exact reviewed content hash.
      </p>

      {mutationError ? (
        <FeedbackBanner
          tone={conflict ? "warning" : "danger"}
          title={conflict ? "This draft changed since it was loaded" : "The action could not be completed"}
          actions={conflict ? <button className="button compact secondary" type="button" onClick={() => void onUpdated()}>Load latest draft</button> : undefined}
        >
          {errorMessage(mutationError, "Try the action again.")}
        </FeedbackBanner>
      ) : null}

      <dl className="approval-facts">
        <div><dt>Version</dt><dd>{plan.number}</dd></div>
        <div><dt>Quality</dt><dd className={plan.quality_status === "passed" ? "positive" : "negative"}>{plan.quality_status}</dd></div>
        <div><dt>Row version</dt><dd>{plan.row_version}</dd></div>
      </dl>
      <div className="hash-panel">
        <span>Content hash</span>
        <code>{plan.content_hash || "Not validated yet"}</code>
      </div>

      {validation ? (
        <section className="validation-result" aria-live="polite">
          <h3>{validation.passed ? "Validation passed" : `${issues.length} validation issue${issues.length === 1 ? "" : "s"}`}</h3>
          {issues.length ? (
            <ol>
              {issues.map((issue, index) => (
                <li className={issue.severity} key={`${issue.code}-${index}`}>
                  <div><strong>{issue.code}</strong><span>{issue.severity}</span></div>
                  <p>{issue.message}</p>
                  <ReferenceLinks references={issue.references} />
                </li>
              ))}
            </ol>
          ) : <p>The persisted graph, schedule, scope, estimates, and coverage checks passed.</p>}
        </section>
      ) : null}

      {plan.state === "draft" ? (
        <div className="approval-actions">
          <button className="button secondary" type="button" disabled={Boolean(activeMutation)} onClick={() => validate.mutate()}>
            {validate.isPending ? "Validating…" : "Validate draft"}
          </button>
          <button
            className="button primary"
            type="button"
            disabled={Boolean(activeMutation) || plan.quality_status !== "passed" || !plan.content_hash}
            onClick={() => submitReview.mutate()}
          >
            {submitReview.isPending ? "Submitting…" : "Submit for review"}
          </button>
          {plan.quality_status !== "passed" ? <small>Validate and resolve every required issue before review.</small> : null}
        </div>
      ) : null}

      {plan.state === "under_review" ? (
        <>
          <FeedbackBanner tone="info" title="Editing is paused during review">
            Request changes to return this version to draft, or approve the exact hash shown above.
          </FeedbackBanner>
          <div className="change-request">
            <label>
              <span>Reason for changes</span>
              <textarea rows={3} value={changeReason} onChange={(event) => setChangeReason(event.target.value)} />
            </label>
            <button
              className="button secondary"
              type="button"
              disabled={Boolean(activeMutation) || changeReason.trim().length < 3}
              onClick={() => requestChanges.mutate()}
            >
              {requestChanges.isPending ? "Returning to draft…" : "Request changes"}
            </button>
          </div>
          {!confirming ? (
            <button className="button primary full-width" type="button" onClick={() => setConfirming(true)}>
              Review approval details
            </button>
          ) : (
            <section className="approval-confirmation" aria-labelledby="confirm-approval-title">
              <h3 id="confirm-approval-title">Confirm activation</h3>
              <p>This makes version {plan.number} the active immutable plan and supersedes any prior active version.</p>
              <label>
                <span>Approval note <small>Optional</small></span>
                <textarea rows={2} value={approvalReason} onChange={(event) => setApprovalReason(event.target.value)} />
              </label>
              <label className="check-row">
                <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                <span>I reviewed version {plan.number} and approve content hash ending {plan.content_hash.slice(-12)}.</span>
              </label>
              <div className="dialog-actions">
                <button className="button secondary" type="button" onClick={() => setConfirming(false)}>Cancel</button>
                <button className="button primary" type="button" disabled={!confirmed || approve.isPending} onClick={() => approve.mutate()}>
                  {approve.isPending ? "Activating…" : "Approve and activate"}
                </button>
              </div>
            </section>
          )}
        </>
      ) : null}

      {plan.state === "active" ? (
        <FeedbackBanner tone="success" title="This plan is active">
          Approval is recorded with the owner, timestamp, version, and exact content hash.
        </FeedbackBanner>
      ) : null}
      {["archived", "superseded"].includes(plan.state) ? (
        <FeedbackBanner tone="info" title="Historical version">
          This immutable snapshot remains available for audit and comparison.
        </FeedbackBanner>
      ) : null}
    </aside>
  );
}
