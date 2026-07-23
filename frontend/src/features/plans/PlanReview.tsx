import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import {
  deleteMilestone,
  deleteTask,
  updateMilestone,
  updateTask,
} from "../../api/plans";
import type { MilestoneView, PlanGraphView, ProjectView, TaskView } from "../../api/types";
import { errorMessage, isConflict } from "../../api/errorUtils";
import { FeedbackBanner, SourceBadge, StateBadge } from "../../components/Feedback";
import { ApprovalPanel } from "./ApprovalPanel";
import { DependencyEditor } from "./DependencyEditor";
import { AnalysisEditor } from "./editors/AnalysisEditor";
import { MilestoneEditor } from "./editors/MilestoneEditor";
import { TaskEditor } from "./editors/TaskEditor";

type EditorState =
  | { type: "analysis" }
  | { type: "milestone"; milestone?: MilestoneView }
  | { type: "task"; task?: TaskView; milestoneId?: string }
  | null;

type DeleteState =
  | { type: "milestone"; item: MilestoneView }
  | { type: "task"; item: TaskView }
  | null;

function recordText(record: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "Structured item";
}

function recordId(record: Record<string, unknown>, index: number): string {
  return recordText(record, "temp_id", "stable_key", "id") === "Structured item"
    ? `ITEM-${index + 1}`
    : recordText(record, "temp_id", "stable_key", "id");
}

interface PlanReviewProps {
  project: ProjectView;
  plan: PlanGraphView;
  onRefresh: () => Promise<void>;
}

export function PlanReview({ project, plan, onRefresh }: PlanReviewProps) {
  const [editor, setEditor] = useState<EditorState>(null);
  const [pendingDelete, setPendingDelete] = useState<DeleteState>(null);
  const canEdit = plan.state === "draft";
  const orderedMilestones = [...plan.milestones].sort((a, b) => a.sequence - b.sequence);
  const mutateItem = useMutation({
    mutationFn: async ({
      kind,
      item,
      value,
    }: {
      kind: "milestone-lock" | "task-lock" | "milestone-sequence";
      item: MilestoneView | TaskView;
      value: boolean | number;
    }) => {
      if (kind === "milestone-lock") {
        return updateMilestone(plan.id, item.id, plan.row_version, { locked: value as boolean });
      }
      if (kind === "milestone-sequence") {
        return updateMilestone(plan.id, item.id, plan.row_version, { sequence: value as number });
      }
      return updateTask(plan.id, item.id, plan.row_version, { locked: value as boolean });
    },
    onSuccess: onRefresh,
  });
  const removeItem = useMutation({
    mutationFn: (target: Exclude<DeleteState, null>) =>
      target.type === "milestone"
        ? deleteMilestone(plan.id, target.item.id, plan.row_version)
        : deleteTask(plan.id, target.item.id, plan.row_version),
    onSuccess: async () => {
      setPendingDelete(null);
      await onRefresh();
    },
  });
  const mutationError = mutateItem.error ?? removeItem.error;

  const moveMilestone = (milestone: MilestoneView, direction: -1 | 1) => {
    const index = orderedMilestones.findIndex((item) => item.id === milestone.id);
    const neighbor = orderedMilestones[index + direction];
    if (neighbor) {
      mutateItem.mutate({
        kind: "milestone-sequence",
        item: milestone,
        value: neighbor.sequence,
      });
    }
  };

  return (
    <div className="review-layout">
      <div className="review-content">
        {editor?.type === "analysis" ? (
          <AnalysisEditor plan={plan} onSaved={onRefresh} onClose={() => setEditor(null)} />
        ) : null}
        {editor?.type === "milestone" ? (
          <MilestoneEditor plan={plan} milestone={editor.milestone} onSaved={onRefresh} onClose={() => setEditor(null)} />
        ) : null}
        {editor?.type === "task" ? (
          <TaskEditor plan={plan} task={editor.task} initialMilestoneId={editor.milestoneId} onSaved={onRefresh} onClose={() => setEditor(null)} />
        ) : null}

        {mutationError ? (
          <FeedbackBanner
            tone={isConflict(mutationError) ? "warning" : "danger"}
            title={isConflict(mutationError) ? "The draft changed elsewhere" : "The item could not be changed"}
            actions={isConflict(mutationError) ? <button className="button compact secondary" type="button" onClick={() => void onRefresh()}>Load latest draft</button> : undefined}
          >
            {errorMessage(mutationError, "Try the change again.")}
          </FeedbackBanner>
        ) : null}
        {!canEdit && plan.state === "under_review" ? (
          <FeedbackBanner tone="info" title="Review mode is read-only">
            Use “Request changes” in the approval panel before editing this version.
          </FeedbackBanner>
        ) : null}

        <section className="review-section analysis-section" aria-labelledby="analysis-title">
          <div className="section-heading-row">
            <div><span className="eyebrow">Plan foundation</span><h2 id="analysis-title">Analysis and scope</h2></div>
            {canEdit ? <button className="button compact secondary" type="button" onClick={() => setEditor({ type: "analysis" })}>Edit analysis</button> : null}
          </div>
          {plan.analysis ? (
            <>
              <p className="analysis-summary">{plan.analysis.summary}</p>
              <dl className="analysis-facts">
                <div><dt>Project type</dt><dd>{plan.analysis.project_type}</dd></div>
                <div><dt>Complexity</dt><dd>{plan.analysis.complexity}</dd></div>
                <div><dt>Intended users</dt><dd>{plan.analysis.intended_users.join(", ") || "Not specified"}</dd></div>
                <div><dt>Workstreams</dt><dd>{plan.analysis.workstreams.join(", ") || "Not specified"}</dd></div>
              </dl>
              <div className="scope-columns">
                <div><h3>MVP boundary</h3>{plan.analysis.mvp_boundary.length ? <ul>{plan.analysis.mvp_boundary.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No MVP boundary items.</p>}</div>
                <div><h3>Excluded scope</h3>{plan.analysis.excluded_scope.length ? <ul>{plan.analysis.excluded_scope.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No exclusions recorded.</p>}</div>
              </div>
            </>
          ) : <div className="inline-empty"><strong>No analysis persisted</strong><span>Planning must persist an analysis before this draft can pass validation.</span></div>}
        </section>

        <section className="review-section" aria-labelledby="modules-title">
          <div className="section-heading-row">
            <div><span className="eyebrow">AI proposed</span><h2 id="modules-title">Modules and assumptions</h2></div>
            <SourceBadge source="ai" />
          </div>
          <div className="module-grid">
            {plan.analysis?.modules.map((module, index) => {
              const id = recordId(module, index);
              return (
                <article id={`entity-${id}`} key={`${id}-${index}`}>
                  <span>{id}</span>
                  <h3>{recordText(module, "name", "title")}</h3>
                  <p>{recordText(module, "description", "objective", "deliverable")}</p>
                </article>
              );
            })}
          </div>
          <div className="assumption-list">
            <h3>Explicit assumptions</h3>
            {plan.analysis?.assumptions.length ? (
              <ol>{plan.analysis.assumptions.map((assumption, index) => <li key={index}><span>A{index + 1}</span><p>{recordText(assumption, "statement", "text", "assumption", "title")}</p></li>)}</ol>
            ) : <p>No assumptions are recorded.</p>}
          </div>
        </section>

        <section className="review-section" aria-labelledby="milestones-title">
          <div className="section-heading-row">
            <div><span className="eyebrow">Delivery structure</span><h2 id="milestones-title">Milestones and tasks</h2><p>Items are presented in dependency-ready list form with keyboard controls.</p></div>
            {canEdit ? <button className="button compact primary" type="button" onClick={() => setEditor({ type: "milestone" })}>Add milestone</button> : null}
          </div>
          {orderedMilestones.length ? (
            <ol className="milestone-list">
              {orderedMilestones.map((milestone, milestoneIndex) => {
                const tasks = plan.tasks.filter((task) => task.milestone_id === milestone.id);
                const previous = orderedMilestones[milestoneIndex - 1];
                const next = orderedMilestones[milestoneIndex + 1];
                return (
                  <li className="milestone-card" id={`entity-${milestone.stable_key}`} key={milestone.id}>
                    <div className="milestone-heading">
                      <div className="sequence-number" aria-label={`Position ${milestone.sequence}`}>{String(milestone.sequence).padStart(2, "0")}</div>
                      <div className="milestone-title">
                        <div className="item-labels">
                          <span>{milestone.stable_key}</span>
                          <SourceBadge source={milestone.source} />
                          {milestone.locked ? <span className="lock-badge">Locked</span> : null}
                        </div>
                        <h3>{milestone.name}</h3>
                        <p>{milestone.description}</p>
                      </div>
                      {canEdit ? (
                        <div className="item-actions">
                          <div className="reorder-buttons" aria-label={`Reorder ${milestone.stable_key}`}>
                            <button
                              className="icon-button"
                              type="button"
                              aria-label={`Move ${milestone.stable_key} earlier`}
                              disabled={!previous || milestone.locked || previous.locked || mutateItem.isPending}
                              onClick={() => moveMilestone(milestone, -1)}
                            >↑</button>
                            <button
                              className="icon-button"
                              type="button"
                              aria-label={`Move ${milestone.stable_key} later`}
                              disabled={!next || milestone.locked || next.locked || mutateItem.isPending}
                              onClick={() => moveMilestone(milestone, 1)}
                            >↓</button>
                          </div>
                          <button className="text-button" type="button" disabled={milestone.locked} onClick={() => setEditor({ type: "milestone", milestone })}>Edit</button>
                          <button className="text-button" type="button" disabled={mutateItem.isPending} onClick={() => mutateItem.mutate({ kind: "milestone-lock", item: milestone, value: !milestone.locked })}>{milestone.locked ? "Unlock" : "Lock"}</button>
                          <button className="text-button danger-text" type="button" disabled={milestone.locked} onClick={() => setPendingDelete({ type: "milestone", item: milestone })}>Delete</button>
                        </div>
                      ) : null}
                    </div>
                    <dl className="milestone-facts">
                      <div><dt>Deliverable</dt><dd>{milestone.deliverable}</dd></div>
                      <div><dt>Effort</dt><dd>{Number(milestone.planned_effort_hours)} hours</dd></div>
                      <div><dt>Schedule</dt><dd>{milestone.planned_start ?? "Not scheduled"} → {milestone.planned_finish ?? milestone.target_date ?? "Not scheduled"}</dd></div>
                    </dl>
                    <div className="criteria-block"><strong>Acceptance criteria</strong><ul>{milestone.acceptance_criteria.map((criterion) => <li key={criterion}>{criterion}</li>)}</ul></div>
                    {pendingDelete?.type === "milestone" && pendingDelete.item.id === milestone.id ? (
                      <div className="inline-confirm" role="alert">
                        <span>Delete {milestone.stable_key} and its {tasks.length} task{tasks.length === 1 ? "" : "s"}?</span>
                        <button className="button compact secondary" type="button" onClick={() => setPendingDelete(null)}>Keep milestone</button>
                        <button className="button compact danger" type="button" disabled={removeItem.isPending} onClick={() => removeItem.mutate(pendingDelete)}>Delete milestone</button>
                      </div>
                    ) : null}
                    <div className="task-list-heading">
                      <h4>Tasks <span>{tasks.length}</span></h4>
                      {canEdit ? <button className="button compact secondary" type="button" onClick={() => setEditor({ type: "task", milestoneId: milestone.id })}>Add task</button> : null}
                    </div>
                    {tasks.length ? (
                      <ul className="task-list">
                        {tasks.map((task) => (
                          <li id={`entity-${task.stable_key}`} key={task.id}>
                            <div className="task-topline">
                              <div className="item-labels"><span>{task.stable_key}</span><SourceBadge source={task.source} />{task.locked ? <span className="lock-badge">Locked</span> : null}</div>
                              {canEdit ? (
                                <div className="item-actions">
                                  <button className="text-button" type="button" disabled={task.locked} onClick={() => setEditor({ type: "task", task })}>Edit</button>
                                  <button className="text-button" type="button" disabled={mutateItem.isPending} onClick={() => mutateItem.mutate({ kind: "task-lock", item: task, value: !task.locked })}>{task.locked ? "Unlock" : "Lock"}</button>
                                  <button className="text-button danger-text" type="button" disabled={task.locked} onClick={() => setPendingDelete({ type: "task", item: task })}>Delete</button>
                                </div>
                              ) : null}
                            </div>
                            <h5>{task.title}</h5>
                            <p>{task.description}</p>
                            <dl className="task-facts">
                              <div><dt>Deliverable</dt><dd>{task.deliverable}</dd></div>
                              <div><dt>Effort</dt><dd>{Number(task.effort_min_hours)} / {Number(task.effort_likely_hours)} / {Number(task.effort_max_hours)} h</dd></div>
                              <div><dt>Priority</dt><dd><SourceBadge source="deterministic">{task.priority_label} · {Number(task.priority_score).toFixed(1)}</SourceBadge></dd></div>
                              <div><dt>Dates</dt><dd><SourceBadge source="deterministic">{task.planned_start ?? "—"} → {task.planned_finish ?? "—"}</SourceBadge></dd></div>
                            </dl>
                            <details><summary>Acceptance and definition of done</summary><div className="details-columns"><div><strong>Acceptance</strong><ul>{task.acceptance_criteria.map((item) => <li key={item}>{item}</li>)}</ul></div><div><strong>Done when</strong><ul>{task.definition_of_done.map((item) => <li key={item}>{item}</li>)}</ul></div></div></details>
                            {pendingDelete?.type === "task" && pendingDelete.item.id === task.id ? (
                              <div className="inline-confirm" role="alert">
                                <span>Delete {task.stable_key}? This cannot be undone after saving.</span>
                                <button className="button compact secondary" type="button" onClick={() => setPendingDelete(null)}>Keep task</button>
                                <button className="button compact danger" type="button" disabled={removeItem.isPending} onClick={() => removeItem.mutate(pendingDelete)}>Delete task</button>
                              </div>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    ) : <div className="inline-empty"><strong>No tasks in this milestone</strong><span>Add at least one actionable leaf task before validation.</span></div>}
                  </li>
                );
              })}
            </ol>
          ) : <div className="inline-empty"><strong>No milestones</strong><span>Add a milestone and actionable tasks before validation.</span></div>}
        </section>

        <DependencyEditor plan={plan} canEdit={canEdit} onSaved={onRefresh} />

        <section className="review-section" aria-labelledby="risks-title">
          <div className="section-heading-row"><div><span className="eyebrow">Planning evidence</span><h2 id="risks-title">Risks</h2></div><span className="count-badge">{plan.risks.length}</span></div>
          {plan.risks.length ? (
            <div className="risk-grid">{plan.risks.map((risk, index) => <article key={index}><span>{recordText(risk, "temp_id", "stable_key", "category")}</span><h3>{recordText(risk, "title", "risk", "description")}</h3><p>{recordText(risk, "mitigation", "response", "impact")}</p></article>)}</div>
          ) : <div className="inline-empty"><strong>No risks persisted</strong><span>Validation will report whether risk coverage is required.</span></div>}
        </section>
      </div>

      <div className="review-sidebar">
        <div className="review-version-card">
          <span className="eyebrow">{project.name}</span>
          <div className="title-with-badge"><h2>Plan version {plan.number}</h2><StateBadge state={plan.state} /></div>
          <p>{plan.reason}</p>
          <dl><div><dt>Milestones</dt><dd>{plan.milestones.length}</dd></div><div><dt>Tasks</dt><dd>{plan.tasks.length}</dd></div><div><dt>Dependencies</dt><dd>{plan.dependencies.length}</dd></div></dl>
        </div>
        <ApprovalPanel plan={plan} onUpdated={onRefresh} />
      </div>
    </div>
  );
}
