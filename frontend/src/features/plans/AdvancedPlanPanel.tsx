import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  advancedKeys,
  comparePlanImpact,
  createRegeneration,
  useRegenerationDecision,
} from "../../api/advanced";
import type {
  PlanGraphView,
  PlanVersionSummary,
  RegenerationProposalView,
} from "../../api/types";
import { errorMessage } from "../../api/errorUtils";
import { FeedbackBanner } from "../../components/Feedback";

export function AdvancedPlanPanel({
  plan,
  versions,
  onRefresh,
}: {
  plan: PlanGraphView;
  versions: PlanVersionSummary[];
  onRefresh: () => Promise<void>;
}) {
  const [comparisonId, setComparisonId] = useState(
    versions.find((item) => item.id !== plan.id)?.id ?? "",
  );
  const [replacementTitle, setReplacementTitle] = useState("");
  const [proposal, setProposal] = useState<RegenerationProposalView | null>(null);
  const comparison = useQuery({
    queryKey: advancedKeys.comparison(comparisonId, plan.id),
    queryFn: () => comparePlanImpact(comparisonId, plan.id),
    enabled: Boolean(comparisonId),
  });
  const eligibleTask = plan.tasks.find(
    (task) => !task.locked && !task.protected && task.source === "ai",
  );
  const regenerate = useMutation({
    mutationFn: () => {
      if (!eligibleTask) throw new Error("No eligible AI task.");
      return createRegeneration(plan.id, {
        targets: [
          {
            entity_type: "task",
            stable_key: eligibleTask.stable_key,
            fields: ["title"],
          },
        ],
        replacements: [
          {
            entity_type: "task",
            stable_key: eligibleTask.stable_key,
            values: { title: replacementTitle },
          },
        ],
      });
    },
    onSuccess: setProposal,
  });
  const decide = useRegenerationDecision(plan.id);

  return (
    <section className="review-section advanced-plan-panel" aria-labelledby="advanced-plan-title">
      <div className="section-heading-row">
        <div>
          <span className="eyebrow">Full-version intelligence</span>
          <h2 id="advanced-plan-title">Compare and selectively regenerate</h2>
        </div>
      </div>
      <p>
        Comparisons use stable keys. Regeneration creates a proposal first and never
        changes an active plan.
      </p>
      {versions.length > 1 ? (
        <div className="advanced-comparison">
          <label>
            <span>Compare current version with</span>
            <select
              value={comparisonId}
              onChange={(event) => setComparisonId(event.target.value)}
            >
              {versions
                .filter((item) => item.id !== plan.id)
                .map((item) => (
                  <option value={item.id} key={item.id}>
                    Version {item.number} · {item.state.replaceAll("_", " ")}
                  </option>
                ))}
            </select>
          </label>
          {comparison.data ? (
            <>
              <dl className="analysis-facts" aria-label="Plan comparison metrics">
                <div><dt>Changed items</dt><dd>{comparison.data.changes.length}</dd></div>
                <div><dt>Schedule delta</dt><dd>{comparison.data.schedule_delta_days ?? "Not available"} days</dd></div>
                <div><dt>Scope delta</dt><dd>{comparison.data.scope_delta}</dd></div>
                <div><dt>Risk delta</dt><dd>{comparison.data.risk_delta}</dd></div>
              </dl>
              <div className="table-scroll" tabIndex={0}>
                <table>
                  <caption>Stable-key version changes</caption>
                  <thead><tr><th>Entity</th><th>Reference</th><th>Change</th></tr></thead>
                  <tbody>
                    {comparison.data.changes.map((change, index) => (
                      <tr key={`${String(change.stable_key)}-${index}`}>
                        <td>{String(change.entity_type)}</td>
                        <td><code>{String(change.stable_key)}</code></td>
                        <td>{String(change.category).replaceAll("_", " ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : comparison.isError ? (
            <FeedbackBanner tone="danger" title="Comparison unavailable">
              {errorMessage(comparison.error, "Try a different version.")}
            </FeedbackBanner>
          ) : <p aria-live="polite">Calculating comparison…</p>}
        </div>
      ) : <p>Create another plan version to compare stable-key changes.</p>}

      {plan.state === "draft" ? (
        <div className="regeneration-control">
          <h3>Selective task-title proposal</h3>
          {eligibleTask ? (
            <>
              <p>Target: <code>{eligibleTask.stable_key}</code>. Locked and owner-edited items are excluded.</p>
              <label>
                <span>Replacement title</span>
                <input
                  value={replacementTitle}
                  minLength={3}
                  maxLength={120}
                  onChange={(event) => setReplacementTitle(event.target.value)}
                />
              </label>
              <button
                type="button"
                className="button secondary"
                disabled={replacementTitle.trim().length < 3 || regenerate.isPending}
                onClick={() => regenerate.mutate()}
              >
                {regenerate.isPending ? "Building proposal…" : "Preview regeneration"}
              </button>
            </>
          ) : <p>No unlocked, unedited AI task is eligible for regeneration.</p>}
          {proposal ? (
            <div className="feedback-banner info">
              <div>
                <strong>Proposal ready — draft unchanged</strong>
                <div className="feedback-copy">
                  {proposal.diff_json.length} change(s); affected references:{" "}
                  {proposal.impact_json.affected_stable_keys?.join(", ") || "none"}.
                </div>
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="button"
                  disabled={decide.isPending}
                  onClick={() =>
                    decide.mutate(
                      { proposal, decision: "approve" },
                      { onSuccess: (updated) => {
                        setProposal(updated);
                        void onRefresh();
                      } },
                    )
                  }
                >Approve exact diff</button>
                <button
                  type="button"
                  className="button secondary"
                  disabled={decide.isPending}
                  onClick={() => decide.mutate({ proposal, decision: "reject" })}
                >Reject</button>
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <FeedbackBanner tone="info" title="Active and reviewed plans are immutable">
          Create a new draft version before requesting selective regeneration.
        </FeedbackBanner>
      )}
    </section>
  );
}
