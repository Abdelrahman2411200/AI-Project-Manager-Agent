import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createMilestone, updateMilestone } from "../../../api/plans";
import type { MilestoneCreatePayload, MilestoneView, PlanGraphView } from "../../../api/types";
import { errorMessage, isConflict } from "../../../api/errorUtils";
import { FeedbackBanner } from "../../../components/Feedback";
import { UnsavedChangesDialog } from "../../../components/UnsavedChangesDialog";
import { useUnsavedChanges } from "../../../hooks/useUnsavedChanges";

const schema = z.object({
  module_refs: z.string().trim().min(1, "Add at least one module reference."),
  name: z.string().trim().min(3).max(120),
  description: z.string().trim().min(20, "Describe this milestone in at least 20 characters.").max(2000),
  objective: z.string().trim().min(10).max(500),
  deliverable: z.string().trim().min(3).max(500),
  sequence: z.coerce.number().int().min(1).max(9999),
  target_date: z.string(),
  planned_effort_hours: z.coerce.number().positive().max(100_000),
  acceptance_criteria: z.string().trim().min(1, "Add at least one acceptance criterion."),
  locked: z.boolean(),
});
type Values = z.infer<typeof schema>;
type Input = z.input<typeof schema>;

function lines(value: string): string[] {
  return value.split("\n").map((line) => line.trim()).filter(Boolean);
}

interface MilestoneEditorProps {
  plan: PlanGraphView;
  milestone?: MilestoneView;
  onSaved: () => Promise<void>;
  onClose: () => void;
}

export function MilestoneEditor({ plan, milestone, onSaved, onClose }: MilestoneEditorProps) {
  const form = useForm<Input, unknown, Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      module_refs: milestone?.module_refs.join("\n") ?? "MOD-001",
      name: milestone?.name ?? "",
      description: milestone?.description ?? "",
      objective: milestone?.objective ?? "",
      deliverable: milestone?.deliverable ?? "",
      sequence: milestone?.sequence ?? plan.milestones.length + 1,
      target_date: milestone?.target_date ?? "",
      planned_effort_hours: Number(milestone?.planned_effort_hours ?? 8),
      acceptance_criteria: milestone?.acceptance_criteria.join("\n") ?? "",
      locked: milestone?.locked ?? false,
    },
  });
  const blocker = useUnsavedChanges(form.formState.isDirty);
  const save = useMutation({
    mutationFn: (values: Values) => {
      const payload: MilestoneCreatePayload = {
        module_refs: lines(values.module_refs),
        name: values.name,
        description: values.description,
        objective: values.objective,
        deliverable: values.deliverable,
        sequence: values.sequence,
        planned_effort_hours: values.planned_effort_hours,
        acceptance_criteria: lines(values.acceptance_criteria),
        locked: values.locked,
      };
      if (values.target_date) payload.target_date = values.target_date;
      return milestone
        ? updateMilestone(plan.id, milestone.id, plan.row_version, payload)
        : createMilestone(plan.id, plan.row_version, payload);
    },
    onSuccess: async () => {
      form.reset(form.getValues());
      await onSaved();
      onClose();
    },
  });
  const submit = form.handleSubmit((values) => save.mutate(values));

  return (
    <>
      <section className="editor-panel" aria-labelledby="milestone-editor-title">
        <div className="editor-header">
          <div>
            <span className="eyebrow">{milestone ? milestone.stable_key : "New milestone"}</span>
            <h2 id="milestone-editor-title">{milestone ? "Edit milestone" : "Add milestone"}</h2>
          </div>
          <button className="icon-button" type="button" aria-label="Close milestone editor" onClick={onClose}>×</button>
        </div>
        {milestone?.locked ? (
          <FeedbackBanner tone="warning" title="This milestone is locked">
            Unlock it from the review list before changing its content.
          </FeedbackBanner>
        ) : null}
        {save.isError ? (
          <FeedbackBanner tone={isConflict(save.error) ? "warning" : "danger"} title={isConflict(save.error) ? "The draft changed elsewhere" : "Milestone was not saved"}>
            {errorMessage(save.error, "Review the milestone fields and try again.")}
          </FeedbackBanner>
        ) : null}
        <form className="editor-form" noValidate onSubmit={(event) => void submit(event)}>
          <div className="editor-grid">
            <label><span>Name</span><input {...form.register("name")} />{form.formState.errors.name ? <small className="field-error">{form.formState.errors.name.message}</small> : null}</label>
            <label><span>Position</span><input type="number" min="1" {...form.register("sequence")} /></label>
            <label className="full-field"><span>Description</span><textarea rows={4} {...form.register("description")} />{form.formState.errors.description ? <small className="field-error">{form.formState.errors.description.message}</small> : null}</label>
            <label><span>Objective</span><textarea rows={4} {...form.register("objective")} /></label>
            <label><span>Primary deliverable</span><textarea rows={4} {...form.register("deliverable")} /></label>
            <label><span>Planned effort (hours)</span><input type="number" min="0.5" step="0.5" {...form.register("planned_effort_hours")} /></label>
            <label><span>Target date</span><input type="date" {...form.register("target_date")} /></label>
            <label><span>Module references <small>One per line</small></span><textarea rows={4} {...form.register("module_refs")} /></label>
            <label><span>Acceptance criteria <small>One per line</small></span><textarea rows={4} {...form.register("acceptance_criteria")} />{form.formState.errors.acceptance_criteria ? <small className="field-error">{form.formState.errors.acceptance_criteria.message}</small> : null}</label>
          </div>
          <label className="check-row"><input type="checkbox" {...form.register("locked")} /><span>Lock after saving to protect this owner-controlled milestone</span></label>
          <div className="editor-actions">
            <button className="button secondary" type="button" onClick={onClose}>Cancel</button>
            <button className="button primary" type="submit" disabled={save.isPending || milestone?.locked}>
              {save.isPending ? "Saving…" : milestone ? "Save milestone" : "Add milestone"}
            </button>
          </div>
        </form>
      </section>
      <UnsavedChangesDialog blocker={blocker} />
    </>
  );
}
