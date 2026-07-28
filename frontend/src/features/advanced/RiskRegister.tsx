import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  advancedKeys,
  createRisk,
  deleteRisk,
  listRisks,
  updateRisk,
} from "../../api/advanced";
import { errorMessage } from "../../api/errorUtils";
import { planKeys } from "../../api/plans";
import type {
  AdvancedRiskView,
  PlanGraphView,
  RiskMutationView,
  RiskPayload,
  RiskRelationView,
} from "../../api/types";
import { FeedbackBanner, LoadingState, StateBadge } from "../../components/Feedback";

interface RiskFormState extends RiskPayload {
  status: AdvancedRiskView["status"];
  pending_relation_type: "" | RiskRelationView["entity_type"];
  pending_relation_ref: string;
  source_refs_text: string;
}

function emptyForm(): RiskFormState {
  return {
    category: "technical",
    description: "",
    probability: "possible",
    impact: "medium",
    trigger: "",
    mitigation: "",
    contingency: "",
    relations: [],
    source_fact_refs: [],
    status: "open",
    pending_relation_type: "",
    pending_relation_ref: "",
    source_refs_text: "",
  };
}

function formFor(risk: AdvancedRiskView): RiskFormState {
  return {
    category: risk.category,
    description: risk.description,
    probability: risk.probability,
    impact: risk.impact,
    trigger: risk.trigger,
    mitigation: risk.mitigation,
    contingency: risk.contingency,
    relations: risk.relations.map((item) => ({
      entity_type: item.entity_type,
      entity_ref: item.entity_ref,
    })),
    source_fact_refs: risk.source_fact_refs,
    status: risk.status,
    pending_relation_type: "",
    pending_relation_ref: "",
    source_refs_text: risk.source_fact_refs.join(", "),
  };
}

function severityLabel(score: number): string {
  if (score >= 9) return "Critical exposure";
  if (score >= 6) return "High exposure";
  if (score >= 3) return "Moderate exposure";
  return "Low exposure";
}

function payloadFrom(form: RiskFormState): RiskPayload {
  return {
    category: form.category,
    description: form.description.trim(),
    probability: form.probability,
    impact: form.impact,
    trigger: form.trigger.trim(),
    mitigation: form.mitigation.trim(),
    contingency: form.contingency.trim(),
    relations: form.relations,
    source_fact_refs: form.source_refs_text
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  };
}

export function RiskRegister({ plan }: { plan: PlanGraphView }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<AdvancedRiskView | "new" | null>(null);
  const [form, setForm] = useState<RiskFormState>(emptyForm);
  const [filter, setFilter] = useState<"all" | AdvancedRiskView["status"]>("all");
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const risks = useQuery({
    queryKey: advancedKeys.risks(plan.id),
    queryFn: () => listRisks(plan.id),
  });
  const updatePlanCache = (result: RiskMutationView) => {
    queryClient.setQueryData<PlanGraphView>(planKeys.detail(plan.id), (current) =>
      current
        ? {
            ...current,
            row_version: result.plan_row_version,
            content_hash: result.plan_content_hash,
            quality_status: "failed",
          }
        : current,
    );
  };
  const save = useMutation({
    mutationFn: () => {
      const payload = payloadFrom(form);
      if (editing && editing !== "new") {
        return updateRisk(plan.id, editing.id, plan.row_version, {
          ...payload,
          status: form.status,
        });
      }
      return createRisk(plan.id, plan.row_version, payload);
    },
    onSuccess: async (result) => {
      updatePlanCache(result);
      setEditing(null);
      setForm(emptyForm());
      await queryClient.invalidateQueries({ queryKey: advancedKeys.risks(plan.id) });
    },
  });
  const remove = useMutation({
    mutationFn: (riskId: string) => deleteRisk(plan.id, riskId, plan.row_version),
    onSuccess: async (result) => {
      queryClient.setQueryData<PlanGraphView>(planKeys.detail(plan.id), (current) =>
        current
          ? {
              ...current,
              row_version: result.plan_row_version,
              content_hash: result.plan_content_hash,
              quality_status: "failed",
            }
          : current,
      );
      setPendingDelete(null);
      await queryClient.invalidateQueries({ queryKey: advancedKeys.risks(plan.id) });
    },
  });
  const relationOptions = useMemo(() => {
    if (form.pending_relation_type === "task") {
      return plan.tasks.map((item) => ({
        value: item.stable_key,
        label: `${item.stable_key} · ${item.title}`,
      }));
    }
    if (form.pending_relation_type === "milestone") {
      return plan.milestones.map((item) => ({
        value: item.stable_key,
        label: `${item.stable_key} · ${item.name}`,
      }));
    }
    if (form.pending_relation_type === "dependency") {
      const taskById = new Map(plan.tasks.map((item) => [item.id, item.stable_key]));
      return plan.dependencies.map((item) => {
        const value = `${taskById.get(item.predecessor_id) ?? "Unknown"}->${taskById.get(item.successor_id) ?? "Unknown"}`;
        return { value, label: value };
      });
    }
    return form.pending_relation_ref
      ? [{ value: form.pending_relation_ref, label: form.pending_relation_ref }]
      : [];
  }, [
    form.pending_relation_ref,
    form.pending_relation_type,
    plan.dependencies,
    plan.milestones,
    plan.tasks,
  ]);
  const pendingRelationExists = form.relations.some(
    (item) =>
      item.entity_type === form.pending_relation_type &&
      item.entity_ref === form.pending_relation_ref,
  );
  const visible = (risks.data ?? [])
    .filter((risk) => filter === "all" || risk.status === filter)
    .sort(
      (left, right) =>
        right.severity - left.severity || left.stable_key.localeCompare(right.stable_key),
    );
  const mutable = plan.state === "draft";

  return (
    <section className="advanced-section risk-register" aria-labelledby="risk-register-heading">
      <div className="advanced-section-heading">
        <div>
          <span className="eyebrow">Version-scoped evidence</span>
          <h2 id="risk-register-heading">Risk register</h2>
          <p>
            Severity is deterministic: probability score multiplied by impact score.
            Relations cannot cross the selected plan version.
          </p>
        </div>
        {mutable ? (
          <button
            className="button"
            type="button"
            onClick={() => {
              setEditing("new");
              setForm(emptyForm());
            }}
          >
            Add risk
          </button>
        ) : (
          <span className="metric-pill">Read-only {plan.state.replaceAll("_", " ")}</span>
        )}
      </div>

      {!mutable ? (
        <FeedbackBanner tone="info" title="Active and reviewed plans remain immutable">
          Create or return to a draft version to add, edit, or remove risk content.
        </FeedbackBanner>
      ) : null}

      <label className="compact-filter">
        <span>Filter risks</span>
        <select
          value={filter}
          onChange={(event) =>
            setFilter(event.target.value as "all" | AdvancedRiskView["status"])
          }
        >
          <option value="all">All statuses</option>
          <option value="open">Open</option>
          <option value="mitigated">Mitigated</option>
          <option value="closed">Closed</option>
        </select>
      </label>

      {risks.isPending ? (
        <LoadingState title="Loading risk register…" />
      ) : risks.isError ? (
        <FeedbackBanner tone="danger" title="Risk register unavailable">
          {errorMessage(risks.error, "Try loading the selected plan again.")}
        </FeedbackBanner>
      ) : visible.length ? (
        <div className="risk-card-grid">
          {visible.map((risk) => (
            <article className={`risk-card severity-${risk.severity}`} key={risk.id}>
              <header>
                <div>
                  <code>{risk.stable_key}</code>
                  <h3>{risk.description}</h3>
                </div>
                <StateBadge state={risk.status} />
              </header>
              <dl>
                <div>
                  <dt>Severity</dt>
                  <dd>{risk.severity} · {severityLabel(risk.severity)}</dd>
                </div>
                <div>
                  <dt>Probability</dt>
                  <dd>{risk.probability}</dd>
                </div>
                <div>
                  <dt>Impact</dt>
                  <dd>{risk.impact}</dd>
                </div>
                <div>
                  <dt>Category</dt>
                  <dd>{risk.category}</dd>
                </div>
              </dl>
              <p><strong>Trigger:</strong> {risk.trigger}</p>
              <p><strong>Mitigation:</strong> {risk.mitigation}</p>
              <p><strong>Contingency:</strong> {risk.contingency}</p>
              <div className="risk-relations">
                <strong>Related evidence</strong>
                {risk.relations.length ? (
                  risk.relations.map((relation) => (
                    <code key={relation.id}>
                      {relation.entity_type}:{relation.entity_ref}
                    </code>
                  ))
                ) : (
                  <span>No entity relation</span>
                )}
              </div>
              {mutable ? (
                <footer>
                  <button
                    className="button compact secondary"
                    type="button"
                    onClick={() => {
                      setEditing(risk);
                      setForm(formFor(risk));
                    }}
                  >
                    Edit {risk.stable_key}
                  </button>
                  {pendingDelete === risk.id ? (
                    <span className="inline-confirmation">
                      <span>Remove this risk?</span>
                      <button
                        className="button compact danger"
                        type="button"
                        disabled={remove.isPending}
                        onClick={() => remove.mutate(risk.id)}
                      >
                        Confirm
                      </button>
                      <button
                        className="text-button"
                        type="button"
                        onClick={() => setPendingDelete(null)}
                      >
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <button
                      className="text-button danger-text"
                      type="button"
                      onClick={() => setPendingDelete(risk.id)}
                    >
                      Remove {risk.stable_key}
                    </button>
                  )}
                </footer>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-inline">
          <strong>No {filter === "all" ? "" : `${filter} `}risks</strong>
          <p>
            {mutable
              ? "Add a risk with a trigger, mitigation, contingency, and optional plan relation."
              : "The selected plan has no risks in this filter."}
          </p>
        </div>
      )}

      {editing ? (
        <div className="risk-editor-shell" role="region" aria-labelledby="risk-editor-title">
          <form
            className="risk-editor"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate();
            }}
          >
            <div className="section-heading-row">
              <div>
                <span className="eyebrow">Draft-only change</span>
                <h3 id="risk-editor-title">
                  {editing === "new" ? "Add risk" : `Edit ${editing.stable_key}`}
                </h3>
              </div>
              <button
                className="text-button"
                type="button"
                onClick={() => {
                  setEditing(null);
                  setForm(emptyForm());
                }}
              >
                Close editor
              </button>
            </div>
            <label className="risk-description-field">
              <span>Description</span>
              <textarea
                required
                minLength={10}
                maxLength={2000}
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
            </label>
            <div className="risk-form-grid">
              <label>
                <span>Category</span>
                <select
                  value={form.category}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      category: event.target.value as AdvancedRiskView["category"],
                    })
                  }
                >
                  {["technical", "schedule", "scope", "dependency", "security", "quality", "external"].map((value) => (
                    <option value={value} key={value}>{value}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Probability</span>
                <select
                  value={form.probability}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      probability: event.target.value as AdvancedRiskView["probability"],
                    })
                  }
                >
                  <option value="unlikely">Unlikely</option>
                  <option value="possible">Possible</option>
                  <option value="likely">Likely</option>
                </select>
              </label>
              <label>
                <span>Impact</span>
                <select
                  value={form.impact}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      impact: event.target.value as AdvancedRiskView["impact"],
                    })
                  }
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
              </label>
              {editing !== "new" ? (
                <label>
                  <span>Status</span>
                  <select
                    value={form.status}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        status: event.target.value as AdvancedRiskView["status"],
                      })
                    }
                  >
                    <option value="open">Open</option>
                    <option value="mitigated">Mitigated</option>
                    <option value="closed">Closed</option>
                  </select>
                </label>
              ) : null}
            </div>
            <label>
              <span>Trigger</span>
              <input
                required
                minLength={3}
                maxLength={500}
                value={form.trigger}
                onChange={(event) => setForm({ ...form, trigger: event.target.value })}
              />
            </label>
            <label>
              <span>Mitigation</span>
              <textarea
                required
                minLength={10}
                maxLength={1000}
                value={form.mitigation}
                onChange={(event) => setForm({ ...form, mitigation: event.target.value })}
              />
            </label>
            <label>
              <span>Contingency</span>
              <textarea
                required
                minLength={10}
                maxLength={1000}
                value={form.contingency}
                onChange={(event) => setForm({ ...form, contingency: event.target.value })}
              />
            </label>
            <fieldset>
              <legend>Optional plan relations</legend>
              {form.relations.length ? (
                <ul className="risk-relation-editor-list" aria-label="Selected plan relations">
                  {form.relations.map((relation) => (
                    <li key={`${relation.entity_type}:${relation.entity_ref}`}>
                      <code>
                        {relation.entity_type}:{relation.entity_ref}
                      </code>
                      <button
                        className="text-button danger-text"
                        type="button"
                        aria-label={`Remove relation ${relation.entity_type}:${relation.entity_ref}`}
                        onClick={() =>
                          setForm({
                            ...form,
                            relations: form.relations.filter(
                              (item) =>
                                item.entity_type !== relation.entity_type ||
                                item.entity_ref !== relation.entity_ref,
                            ),
                          })
                        }
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="advanced-note">No plan relations selected.</p>
              )}
              <div className="risk-form-grid">
                <label>
                  <span>New relation type</span>
                  <select
                    value={form.pending_relation_type}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        pending_relation_type: event.target
                          .value as RiskFormState["pending_relation_type"],
                        pending_relation_ref: "",
                      })
                    }
                  >
                    <option value="">No relation</option>
                    <option value="task">Task</option>
                    <option value="milestone">Milestone</option>
                    <option value="dependency">Dependency</option>
                    <option value="requirement">Requirement</option>
                  </select>
                </label>
                <label>
                  <span>New entity reference</span>
                  {form.pending_relation_type === "requirement" ? (
                    <input
                      value={form.pending_relation_ref}
                      minLength={3}
                      maxLength={80}
                      onChange={(event) =>
                        setForm({ ...form, pending_relation_ref: event.target.value })
                      }
                    />
                  ) : (
                    <select
                      disabled={!form.pending_relation_type}
                      value={form.pending_relation_ref}
                      onChange={(event) =>
                        setForm({ ...form, pending_relation_ref: event.target.value })
                      }
                    >
                      <option value="">Select a reference</option>
                      {relationOptions.map((option) => (
                        <option value={option.value} key={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  )}
                </label>
              </div>
              <button
                className="button compact secondary"
                type="button"
                disabled={
                  !form.pending_relation_type ||
                  form.pending_relation_ref.length < 3 ||
                  pendingRelationExists ||
                  form.relations.length >= 50
                }
                onClick={() => {
                  if (!form.pending_relation_type || !form.pending_relation_ref) return;
                  setForm({
                    ...form,
                    relations: [
                      ...form.relations,
                      {
                        entity_type: form.pending_relation_type,
                        entity_ref: form.pending_relation_ref,
                      },
                    ],
                    pending_relation_type: "",
                    pending_relation_ref: "",
                  });
                }}
              >
                {pendingRelationExists ? "Relation already selected" : "Add relation"}
              </button>
            </fieldset>
            <label>
              <span>Source fact references</span>
              <input
                value={form.source_refs_text}
                placeholder="CONSTRAINT-001, REQ-002"
                onChange={(event) =>
                  setForm({ ...form, source_refs_text: event.target.value })
                }
              />
            </label>
            {save.isError ? (
              <FeedbackBanner tone="danger" title="Risk could not be saved">
                {errorMessage(save.error, "Review the fields and plan version, then try again.")}
              </FeedbackBanner>
            ) : null}
            <button className="button" type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : editing === "new" ? "Add risk" : "Save risk"}
            </button>
          </form>
        </div>
      ) : null}
      {remove.isError ? (
        <FeedbackBanner tone="danger" title="Risk could not be removed">
          {errorMessage(remove.error, "Refresh the plan version and try again.")}
        </FeedbackBanner>
      ) : null}
    </section>
  );
}
