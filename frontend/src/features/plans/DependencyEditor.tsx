import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createDependency, deleteDependency } from "../../api/plans";
import type { DependencyView, PlanGraphView } from "../../api/types";
import { errorMessage, isConflict } from "../../api/errorUtils";
import { FeedbackBanner, SourceBadge } from "../../components/Feedback";

const schema = z
  .object({
    predecessor_id: z.string().uuid("Choose a predecessor task."),
    successor_id: z.string().uuid("Choose a successor task."),
    reason: z.string().trim().min(10, "Explain the dependency in at least 10 characters.").max(1000),
    confidence_label: z.enum(["low", "medium", "high"]),
  })
  .refine((value) => value.predecessor_id !== value.successor_id, {
    path: ["successor_id"],
    message: "Choose two different tasks.",
  });
type Values = z.infer<typeof schema>;

interface DependencyEditorProps {
  plan: PlanGraphView;
  canEdit: boolean;
  onSaved: () => Promise<void>;
}

export function DependencyEditor({ plan, canEdit, onSaved }: DependencyEditorProps) {
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      predecessor_id: plan.tasks[0]?.id ?? "",
      successor_id: plan.tasks[1]?.id ?? "",
      reason: "",
      confidence_label: "medium",
    },
  });
  const create = useMutation({
    mutationFn: (values: Values) => {
      const predecessor = plan.tasks.find((task) => task.id === values.predecessor_id);
      const successor = plan.tasks.find((task) => task.id === values.successor_id);
      return createDependency(plan.id, plan.row_version, {
        ...values,
        evidence_refs: [predecessor?.stable_key, successor?.stable_key].filter(
          (value): value is string => Boolean(value),
        ),
      });
    },
    onSuccess: async () => {
      form.reset({ ...form.getValues(), reason: "" });
      await onSaved();
    },
  });
  const remove = useMutation({
    mutationFn: (dependency: DependencyView) =>
      deleteDependency(plan.id, dependency.id, plan.row_version),
    onSuccess: async () => {
      setPendingDelete(null);
      await onSaved();
    },
  });
  const taskById = new Map(plan.tasks.map((task) => [task.id, task]));
  const mutationError = create.error ?? remove.error;
  const submit = form.handleSubmit((values) => create.mutate(values));

  return (
    <section className="review-section" aria-labelledby="dependencies-title">
      <div className="section-heading-row">
        <div>
          <span className="eyebrow">Graph rules</span>
          <h2 id="dependencies-title">Dependencies</h2>
          <p>Finish-to-start edges are validated for cycles before they are saved.</p>
        </div>
        <span className="count-badge">{plan.dependencies.length}</span>
      </div>
      {mutationError ? (
        <FeedbackBanner tone={isConflict(mutationError) ? "warning" : "danger"} title={isConflict(mutationError) ? "Dependency conflicts with the latest draft" : "Dependency could not be changed"}>
          {errorMessage(mutationError, "Review the dependency and try again.")}
        </FeedbackBanner>
      ) : null}
      {plan.dependencies.length ? (
        <ol className="dependency-list">
          {plan.dependencies.map((dependency) => {
            const predecessor = taskById.get(dependency.predecessor_id);
            const successor = taskById.get(dependency.successor_id);
            return (
              <li key={dependency.id}>
                <div className="dependency-path">
                  <a href={`#entity-${predecessor?.stable_key}`}>{predecessor?.stable_key ?? "Unknown task"}</a>
                  <span aria-label="must finish before">→</span>
                  <a href={`#entity-${successor?.stable_key}`}>{successor?.stable_key ?? "Unknown task"}</a>
                </div>
                <p>{dependency.reason}</p>
                <div className="item-meta">
                  <SourceBadge source={dependency.source} />
                  <span>{dependency.confidence_label} confidence</span>
                </div>
                {canEdit ? (
                  pendingDelete === dependency.id ? (
                    <div className="inline-confirm" role="alert">
                      <span>Remove this dependency?</span>
                      <button className="button compact secondary" type="button" onClick={() => setPendingDelete(null)}>Keep</button>
                      <button className="button compact danger" type="button" disabled={remove.isPending} onClick={() => remove.mutate(dependency)}>Remove</button>
                    </div>
                  ) : (
                    <button className="text-button danger-text" type="button" onClick={() => setPendingDelete(dependency.id)}>Remove dependency</button>
                  )
                ) : null}
              </li>
            );
          })}
        </ol>
      ) : (
        <div className="inline-empty"><strong>No dependencies</strong><span>Tasks can proceed independently unless an edge is added.</span></div>
      )}
      {canEdit && plan.tasks.length >= 2 ? (
        <form className="dependency-form" noValidate onSubmit={(event) => void submit(event)}>
          <h3>Add dependency</h3>
          <div className="editor-grid">
            <label><span>Predecessor</span><select {...form.register("predecessor_id")}>{plan.tasks.map((task) => <option key={task.id} value={task.id}>{task.stable_key} · {task.title}</option>)}</select></label>
            <label><span>Successor</span><select {...form.register("successor_id")}>{plan.tasks.map((task) => <option key={task.id} value={task.id}>{task.stable_key} · {task.title}</option>)}</select>{form.formState.errors.successor_id ? <small className="field-error">{form.formState.errors.successor_id.message}</small> : null}</label>
            <label className="full-field"><span>Reason</span><textarea rows={3} {...form.register("reason")} />{form.formState.errors.reason ? <small className="field-error">{form.formState.errors.reason.message}</small> : null}</label>
            <label><span>Confidence</span><select {...form.register("confidence_label")}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label>
          </div>
          <button className="button compact secondary" type="submit" disabled={create.isPending}>{create.isPending ? "Adding…" : "Add dependency"}</button>
        </form>
      ) : null}
    </section>
  );
}
