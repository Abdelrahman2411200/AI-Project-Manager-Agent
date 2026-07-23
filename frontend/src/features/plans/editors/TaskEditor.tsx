import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createTask, updateTask } from "../../../api/plans";
import type { PlanGraphView, PriorityFactorsPayload, TaskCreatePayload, TaskView } from "../../../api/types";
import { errorMessage, isConflict } from "../../../api/errorUtils";
import { FeedbackBanner } from "../../../components/Feedback";
import { UnsavedChangesDialog } from "../../../components/UnsavedChangesDialog";
import { useUnsavedChanges } from "../../../hooks/useUnsavedChanges";

const schema = z
  .object({
    milestone_id: z.string().uuid("Choose a milestone."),
    parent_id: z.string(),
    title: z.string().trim().min(3).max(120),
    description: z.string().trim().min(20, "Describe the task in at least 20 characters.").max(2000),
    deliverable: z.string().trim().min(3).max(500),
    acceptance_criteria: z.string().trim().min(1, "Add an observable acceptance criterion."),
    definition_of_done: z.string().trim().min(1, "Add at least one definition-of-done item."),
    effort_min_hours: z.coerce.number().positive(),
    effort_likely_hours: z.coerce.number().positive(),
    effort_max_hours: z.coerce.number().positive(),
    complexity: z.enum(["trivial", "low", "medium", "high"]),
    workstreams: z.string().trim().min(1),
    skill_tags: z.string(),
    requirement_refs: z.string(),
    assumption_refs: z.string(),
    mvp_necessity: z.coerce.number().int().min(0).max(100),
    deadline_urgency: z.coerce.number().int().min(0).max(100),
    user_value: z.coerce.number().int().min(0).max(100),
    risk_reduction: z.coerce.number().int().min(0).max(100),
    user_preference: z.coerce.number().int().min(0).max(100),
    locked: z.boolean(),
  })
  .refine(
    (value) =>
      value.effort_min_hours <= value.effort_likely_hours &&
      value.effort_likely_hours <= value.effort_max_hours,
    { path: ["effort_likely_hours"], message: "Effort must satisfy minimum ≤ likely ≤ maximum." },
  );

type Values = z.infer<typeof schema>;
type Input = z.input<typeof schema>;

function lines(value: string): string[] {
  return value.split("\n").map((line) => line.trim()).filter(Boolean);
}

function priorityValue(task: TaskView | undefined, key: keyof PriorityFactorsPayload): number {
  const value = task?.priority_breakdown[key];
  return typeof value === "number" ? value : 50;
}

interface TaskEditorProps {
  plan: PlanGraphView;
  task?: TaskView;
  initialMilestoneId?: string;
  onSaved: () => Promise<void>;
  onClose: () => void;
}

export function TaskEditor({ plan, task, initialMilestoneId, onSaved, onClose }: TaskEditorProps) {
  const form = useForm<Input, unknown, Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      milestone_id: task?.milestone_id ?? initialMilestoneId ?? plan.milestones[0]?.id ?? "",
      parent_id: task?.parent_id ?? "",
      title: task?.title ?? "",
      description: task?.description ?? "",
      deliverable: task?.deliverable ?? "",
      acceptance_criteria: task?.acceptance_criteria.join("\n") ?? "",
      definition_of_done: task?.definition_of_done.join("\n") ?? "",
      effort_min_hours: Number(task?.effort_min_hours ?? 4),
      effort_likely_hours: Number(task?.effort_likely_hours ?? 8),
      effort_max_hours: Number(task?.effort_max_hours ?? 12),
      complexity: task?.complexity ?? "medium",
      workstreams: task?.workstreams.join("\n") ?? "",
      skill_tags: task?.skill_tags.join("\n") ?? "",
      requirement_refs: task?.requirement_refs.join("\n") ?? "",
      assumption_refs: task?.assumption_refs.join("\n") ?? "",
      mvp_necessity: priorityValue(task, "mvp_necessity"),
      deadline_urgency: priorityValue(task, "deadline_urgency"),
      user_value: priorityValue(task, "user_value"),
      risk_reduction: priorityValue(task, "risk_reduction"),
      user_preference: priorityValue(task, "user_preference"),
      locked: task?.locked ?? false,
    },
  });
  const blocker = useUnsavedChanges(form.formState.isDirty);
  const save = useMutation({
    mutationFn: (values: Values) => {
      const payload: TaskCreatePayload = {
        milestone_id: values.milestone_id,
        parent_id: values.parent_id || null,
        title: values.title,
        description: values.description,
        deliverable: values.deliverable,
        acceptance_criteria: lines(values.acceptance_criteria),
        definition_of_done: lines(values.definition_of_done),
        effort_min_hours: values.effort_min_hours,
        effort_likely_hours: values.effort_likely_hours,
        effort_max_hours: values.effort_max_hours,
        complexity: values.complexity,
        workstreams: lines(values.workstreams),
        skill_tags: lines(values.skill_tags),
        requirement_refs: lines(values.requirement_refs),
        assumption_refs: lines(values.assumption_refs),
        priority_factors: {
          mvp_necessity: values.mvp_necessity,
          deadline_urgency: values.deadline_urgency,
          user_value: values.user_value,
          risk_reduction: values.risk_reduction,
          user_preference: values.user_preference,
        },
        locked: values.locked,
      };
      return task
        ? updateTask(plan.id, task.id, plan.row_version, payload)
        : createTask(plan.id, plan.row_version, payload);
    },
    onSuccess: async () => {
      form.reset(form.getValues());
      await onSaved();
      onClose();
    },
  });
  const submit = form.handleSubmit((values) => save.mutate(values));
  const possibleParents = plan.tasks.filter((candidate) => candidate.id !== task?.id);

  return (
    <>
      <section className="editor-panel" aria-labelledby="task-editor-title">
        <div className="editor-header">
          <div>
            <span className="eyebrow">{task ? task.stable_key : "New task"}</span>
            <h2 id="task-editor-title">{task ? "Edit task" : "Add actionable task"}</h2>
          </div>
          <button className="icon-button" type="button" aria-label="Close task editor" onClick={onClose}>×</button>
        </div>
        {task?.locked ? (
          <FeedbackBanner tone="warning" title="This task is locked">
            Unlock it from the review list before changing its content.
          </FeedbackBanner>
        ) : null}
        {save.isError ? (
          <FeedbackBanner tone={isConflict(save.error) ? "warning" : "danger"} title={isConflict(save.error) ? "The draft changed elsewhere" : "Task was not saved"}>
            {errorMessage(save.error, "Review the task fields and try again.")}
          </FeedbackBanner>
        ) : null}
        <form className="editor-form" noValidate onSubmit={(event) => void submit(event)}>
          <div className="editor-grid">
            <label><span>Task title</span><input {...form.register("title")} />{form.formState.errors.title ? <small className="field-error">{form.formState.errors.title.message}</small> : null}</label>
            <label><span>Milestone</span><select {...form.register("milestone_id")}>{plan.milestones.map((milestone) => <option key={milestone.id} value={milestone.id}>{milestone.stable_key} · {milestone.name}</option>)}</select></label>
            <label className="full-field"><span>Description</span><textarea rows={4} {...form.register("description")} />{form.formState.errors.description ? <small className="field-error">{form.formState.errors.description.message}</small> : null}</label>
            <label><span>Primary deliverable</span><textarea rows={4} {...form.register("deliverable")} /></label>
            <label><span>Parent task <small>Optional</small></span><select {...form.register("parent_id")}><option value="">No parent task</option>{possibleParents.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.stable_key} · {candidate.title}</option>)}</select></label>
            <label><span>Acceptance criteria <small>One per line</small></span><textarea rows={5} {...form.register("acceptance_criteria")} />{form.formState.errors.acceptance_criteria ? <small className="field-error">{form.formState.errors.acceptance_criteria.message}</small> : null}</label>
            <label><span>Definition of done <small>One per line</small></span><textarea rows={5} {...form.register("definition_of_done")} />{form.formState.errors.definition_of_done ? <small className="field-error">{form.formState.errors.definition_of_done.message}</small> : null}</label>
          </div>

          <fieldset className="effort-fieldset">
            <legend>Effort estimate in hours</legend>
            <div className="three-column-grid">
              <label><span>Minimum</span><input type="number" min="0.5" step="0.5" {...form.register("effort_min_hours")} /></label>
              <label><span>Likely</span><input type="number" min="0.5" step="0.5" {...form.register("effort_likely_hours")} />{form.formState.errors.effort_likely_hours ? <small className="field-error">{form.formState.errors.effort_likely_hours.message}</small> : null}</label>
              <label><span>Maximum</span><input type="number" min="0.5" step="0.5" {...form.register("effort_max_hours")} /></label>
            </div>
          </fieldset>

          <div className="editor-grid">
            <label><span>Complexity</span><select {...form.register("complexity")}><option value="trivial">Trivial</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label>
            <label><span>Workstreams <small>One per line, maximum 3</small></span><textarea rows={3} {...form.register("workstreams")} /></label>
            <label><span>Skill tags <small>One per line</small></span><textarea rows={3} {...form.register("skill_tags")} /></label>
            <label><span>Requirement references <small>One per line</small></span><textarea rows={3} {...form.register("requirement_refs")} /></label>
            <label><span>Assumption references <small>One per line</small></span><textarea rows={3} {...form.register("assumption_refs")} /></label>
          </div>

          <fieldset className="priority-fieldset">
            <legend>Priority factors</legend>
            <p>These inputs are scored deterministically after validation.</p>
            <div className="priority-grid">
              {([
                ["mvp_necessity", "MVP necessity"],
                ["deadline_urgency", "Deadline urgency"],
                ["user_value", "User value"],
                ["risk_reduction", "Risk reduction"],
                ["user_preference", "Owner preference"],
              ] as const).map(([name, label]) => (
                <label key={name}><span>{label}</span><input type="number" min="0" max="100" {...form.register(name)} /></label>
              ))}
            </div>
          </fieldset>
          <label className="check-row"><input type="checkbox" {...form.register("locked")} /><span>Lock after saving to protect this owner-controlled task</span></label>
          <div className="editor-actions">
            <button className="button secondary" type="button" onClick={onClose}>Cancel</button>
            <button className="button primary" type="submit" disabled={save.isPending || task?.locked}>
              {save.isPending ? "Saving…" : task ? "Save task" : "Add task"}
            </button>
          </div>
        </form>
      </section>
      <UnsavedChangesDialog blocker={blocker} />
    </>
  );
}
