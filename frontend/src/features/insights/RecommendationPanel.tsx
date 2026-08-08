import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  useRecommendationDecision,
  useRecommendations,
} from "../../api/insights";
import type { RecommendationView } from "../../api/types";
import { errorMessage } from "../../api/errorUtils";
import { FeedbackBanner, StateBadge } from "../../components/Feedback";
import { StructuredValue } from "../../components/StructuredValue";
import { evidenceReferenceLabel, humanizeLabel } from "../../utils/display";

export function RecommendationPanel({ projectId }: { projectId: string }) {
  const query = useRecommendations(projectId);
  const mutation = useRecommendationDecision(projectId);
  const [selected, setSelected] = useState<RecommendationView | null>(null);
  const [decision, setDecision] = useState<"accept" | "dismiss" | "defer">("accept");
  const [reason, setReason] = useState("");
  const [deferUntil, setDeferUntil] = useState("");
  const firstField = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (selected) firstField.current?.focus();
  }, [selected]);

  if (query.isPending) {
    return <section className="recommendation-panel" aria-busy="true">Loading grounded recommendations…</section>;
  }
  if (query.isError) {
    return (
      <FeedbackBanner tone="danger" title="Recommendations are unavailable">
        <p>{errorMessage(query.error, "Try recalculating project health.")}</p>
      </FeedbackBanner>
    );
  }
  const open = query.data.filter((item) => item.state === "open" || item.state === "deferred");

  return (
    <section className="recommendation-panel" aria-labelledby="recommendation-heading">
      <header className="section-heading split">
        <div>
          <span className="eyebrow">Evidence-backed guidance</span>
          <h2 id="recommendation-heading">Recommended actions</h2>
          <p>Each suggestion is grounded in the current approved plan. Decisions never edit it.</p>
        </div>
        <span className="recommendation-count">{open.length} actionable</span>
      </header>
      {open.length ? (
        <ul className="recommendation-list">
          {open.map((item) => (
            <li key={item.id} className={`recommendation-card urgency-${item.urgency}`}>
              <div className="recommendation-card-header">
                <div>
                  <span className="task-key">{humanizeLabel(item.detection_code)}</span>
                  <h3>{item.suggested_action}</h3>
                </div>
                <div className="recommendation-badges">
                  <StateBadge state={item.urgency} />
                  <span className="source-badge deterministic">
                    {item.explanation_source === "ai" ? "AI wording · validated" : "Calculated"}
                  </span>
                </div>
              </div>
              <p>{item.why_it_matters}</p>
              <dl className="recommendation-facts">
                <div><dt>Expected impact</dt><dd>{item.expected_impact}</dd></div>
                <div><dt>Risk</dt><dd>{item.risk}</dd></div>
                <div><dt>Verify</dt><dd>{item.verification_step}</dd></div>
              </dl>
              <details>
                <summary>Inspect {item.evidence.length} evidence fact{item.evidence.length === 1 ? "" : "s"}</summary>
                <ul className="recommendation-evidence">
                  {item.evidence.map((fact) => (
                    <li key={fact.id}>
                      <div>
                        <strong title={fact.entity_ref}>{evidenceReferenceLabel(fact.entity_ref)}</strong>
                        <span>{humanizeLabel(fact.entity_type)} · {humanizeLabel(fact.fact_key)}</span>
                      </div>
                      <StructuredValue value={fact.fact_value} />
                    </li>
                  ))}
                </ul>
              </details>
              <div className="task-actions">
                {(["accept", "defer", "dismiss"] as const).map((action) => (
                  <button
                    className={`button compact ${action === "accept" ? "primary" : "secondary"}`}
                    key={action}
                    type="button"
                    onClick={() => {
                      setSelected(item);
                      setDecision(action);
                    }}
                  >
                    {action === "accept" ? "Accept guidance" : action === "defer" ? "Defer" : "Dismiss"}
                  </button>
                ))}
                {item.evidence.some((fact) => fact.entity_ref.startsWith("TASK-")) ? (
                  <Link className="button compact ghost" to={`/projects/${projectId}/board`}>
                    Open board
                  </Link>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="empty-inline">
          <strong>No actionable recommendations</strong>
          <p>Monitoring has not detected a grounded action, or all suggestions were decided.</p>
        </div>
      )}

      {selected ? (
        <div className="dialog-backdrop">
          <section
            className="confirmation-dialog recommendation-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="recommendation-decision-title"
          >
            <span className="eyebrow">Owner decision</span>
            <h2 id="recommendation-decision-title">
              {decision === "accept" ? "Accept this guidance?" : decision === "defer" ? "Defer this guidance?" : "Dismiss this guidance?"}
            </h2>
            <p>
              This records your decision in the audit trail. It does not mutate tasks,
              dates, dependencies, or the active plan.
            </p>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                mutation.mutate(
                  { recommendation: selected, decision, reason, deferUntil },
                  {
                    onSuccess: () => {
                      setSelected(null);
                      setReason("");
                      setDeferUntil("");
                    },
                  },
                );
              }}
            >
              <label>
                Reason (optional)
                <textarea
                  ref={firstField}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  maxLength={1000}
                  rows={3}
                />
              </label>
              {decision === "defer" ? (
                <label>
                  Review again on
                  <input
                    type="date"
                    required
                    value={deferUntil}
                    onChange={(event) => setDeferUntil(event.target.value)}
                  />
                </label>
              ) : null}
              {mutation.isError ? (
                <FeedbackBanner tone="danger" title="Decision was not saved">
                  <p>{errorMessage(mutation.error, "Reload the current recommendation and retry.")}</p>
                </FeedbackBanner>
              ) : null}
              <div className="editor-actions">
                <button className="button secondary" type="button" onClick={() => setSelected(null)}>
                  Cancel
                </button>
                <button className="button primary" type="submit" disabled={mutation.isPending}>
                  {mutation.isPending ? "Saving…" : "Record decision"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </section>
  );
}
