import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";

import { ApiError } from "../api/client";
import { createProject, projectKeys } from "../api/projects";
import { runKeys, startPlanningRun } from "../api/runs";
import type { ProjectCreatePayload } from "../api/types";

const schema = z
  .object({
    name: z.string().trim().min(1, "Project name is required.").max(120),
    goal: z.string().trim().min(1, "Describe the project goal.").max(4000),
    desired_outcome: z.string().max(4000),
    start_date: z.string(),
    deadline: z.string(),
    timezone: z.string().min(1, "A valid IANA timezone is required."),
    capacity_hours_per_week: z.coerce.number().positive().max(168),
    team_size: z.coerce.number().int().min(1).max(100),
    required_features: z.string(),
    excluded_features: z.string(),
    constraints: z.string(),
    notes: z.string().max(8000),
  })
  .refine(
    (value) => !value.start_date || !value.deadline || value.deadline >= value.start_date,
    { path: ["deadline"], message: "Deadline must be on or after the start date." },
  );

type FormValues = z.infer<typeof schema>;
type FormInput = z.input<typeof schema>;

function lines(value: string): string[] {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

export function CreateProjectPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showErrorSummary, setShowErrorSummary] = useState(false);
  const form = useForm<FormInput, unknown, FormValues>({
    resolver: zodResolver(schema),
    shouldFocusError: true,
    defaultValues: {
      name: "",
      goal: "",
      desired_outcome: "",
      start_date: "",
      deadline: "",
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      capacity_hours_per_week: 40,
      team_size: 1,
      required_features: "",
      excluded_features: "",
      constraints: "",
      notes: "",
    },
  });
  const mutation = useMutation({
    mutationFn: async ({ payload, start }: { payload: ProjectCreatePayload; start: boolean }) => {
      const project = await createProject(payload);
      if (!start) return { project, run: null };
      const run = await startPlanningRun(project.id);
      return { project, run };
    },
    onSuccess: ({ project, run }) => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
      queryClient.setQueryData(projectKeys.detail(project.id), project);
      if (run) {
        queryClient.setQueryData(runKeys.detail(run.id), run);
        void navigate(`/projects/${project.id}/planning?run=${run.id}`);
      } else {
        void navigate(`/projects/${project.id}`);
      }
    },
  });
  const submit = (start: boolean) => form.handleSubmit(
    (values) => {
      setShowErrorSummary(false);
      const payload: ProjectCreatePayload = {
        name: values.name,
        goal: values.goal,
        timezone: values.timezone,
        capacity_hours_per_week: values.capacity_hours_per_week,
        team_size: values.team_size,
        requirements: [
          ...lines(values.required_features).map((text) => ({
            kind: "stated" as const,
            text,
            status: "confirmed" as const,
          })),
          ...lines(values.excluded_features).map((text) => ({
            kind: "excluded" as const,
            text,
            status: "confirmed" as const,
          })),
        ],
        constraints: lines(values.constraints).map((text) => ({
          constraint_type: "delivery",
          value_json: { text },
          source: "user" as const,
          confirmed: true,
        })),
        work_calendar: {
          weekday_hours: {
            monday: 8,
            tuesday: 8,
            wednesday: 8,
            thursday: 8,
            friday: 8,
          },
          holidays: [],
          parallel_limit: values.team_size,
        },
      };
      if (values.desired_outcome) payload.desired_outcome = values.desired_outcome;
      if (values.start_date) payload.start_date = values.start_date;
      if (values.deadline) payload.deadline = values.deadline;
      if (values.notes) payload.notes = values.notes;
      mutation.mutate({ payload, start });
    },
    () => {
      setShowErrorSummary(true);
      window.setTimeout(() => document.getElementById("project-error-summary")?.focus(), 0);
    },
  );
  const serverMessage =
    mutation.error instanceof ApiError ? mutation.error.problem.detail : undefined;

  return (
    <div className="form-page">
      <header className="page-header compact">
        <div><span className="eyebrow">Project intake</span><h1>Create a new project</h1><p>Start with what you know. Missing noncritical details can be clarified later.</p></div>
        <Link className="text-link" to="/projects">Cancel</Link>
      </header>
      <form className="project-form" onSubmit={(event) => void submit(true)(event)} noValidate>
        {serverMessage ? <div className="form-alert" role="alert">{serverMessage}</div> : null}
        {showErrorSummary && Object.keys(form.formState.errors).length ? (
          <div className="form-error-summary" id="project-error-summary" role="alert" tabIndex={-1}>
            <strong>Review the highlighted project details</strong>
            <ul>
              {Object.entries(form.formState.errors).map(([field, error]) => (
                <li key={field}><a href={`#project-${field}`}>{error?.message ?? `${field.replaceAll("_", " ")} is invalid.`}</a></li>
              ))}
            </ul>
          </div>
        ) : null}
        <section className="form-section" aria-labelledby="intent-heading">
          <div className="form-section-heading"><span>01</span><div><h2 id="intent-heading">Intent</h2><p>Define the outcome the project must achieve.</p></div></div>
          <div className="form-grid">
            <label className="full-field"><span>Project name *</span><input id="project-name" required {...form.register("name")} />{form.formState.errors.name ? <small className="field-error">{form.formState.errors.name.message}</small> : null}</label>
            <label className="full-field"><span>Goal *</span><textarea id="project-goal" rows={4} {...form.register("goal")} />{form.formState.errors.goal ? <small className="field-error">{form.formState.errors.goal.message}</small> : null}</label>
            <label className="full-field"><span>Desired outcome</span><textarea rows={3} {...form.register("desired_outcome")} /></label>
          </div>
        </section>
        <section className="form-section" aria-labelledby="delivery-heading">
          <div className="form-section-heading"><span>02</span><div><h2 id="delivery-heading">Delivery frame</h2><p>Set time, team, and weekly capacity.</p></div></div>
          <div className="form-grid">
            <label><span>Start date</span><input type="date" {...form.register("start_date")} /></label>
            <label><span>Deadline</span><input id="project-deadline" type="date" aria-describedby="deadline-help" {...form.register("deadline")} /><small id="deadline-help">Must be on or after the start date.</small>{form.formState.errors.deadline ? <small className="field-error">{form.formState.errors.deadline.message}</small> : null}</label>
            <label><span>Team size</span><input type="number" min="1" max="100" {...form.register("team_size")} /></label>
            <label><span>Hours per week</span><input type="number" min="1" max="168" step="0.5" {...form.register("capacity_hours_per_week")} /></label>
            <label className="full-field"><span>IANA timezone</span><input id="project-timezone" aria-describedby="timezone-help" {...form.register("timezone")} /><small id="timezone-help">Use a location identifier such as Africa/Cairo or Europe/London.</small>{form.formState.errors.timezone ? <small className="field-error">{form.formState.errors.timezone.message}</small> : null}</label>
          </div>
        </section>
        <section className="form-section" aria-labelledby="scope-heading">
          <div className="form-section-heading"><span>03</span><div><h2 id="scope-heading">Scope signals</h2><p>Enter one feature or constraint per line.</p></div></div>
          <div className="form-grid">
            <label><span>Required features</span><textarea rows={5} placeholder={"Authentication\nProject planning"} {...form.register("required_features")} /></label>
            <label><span>Excluded features</span><textarea rows={5} placeholder={"Portfolio management\nExternal automation"} {...form.register("excluded_features")} /></label>
            <label className="full-field"><span>Delivery constraints <small>One constraint per line</small></span><textarea rows={4} placeholder={"Must run on the university lab network\nNo external user data"} {...form.register("constraints")} /></label>
            <label className="full-field"><span>Additional notes</span><textarea rows={4} {...form.register("notes")} /></label>
          </div>
        </section>
        <div className="form-actions">
          <Link className="button secondary" to="/projects">Cancel</Link>
          <button className="button secondary" type="button" disabled={mutation.isPending} onClick={(event) => void submit(false)(event)}>
            {mutation.isPending && mutation.variables?.start === false ? "Saving project…" : "Save project"}
          </button>
          <button className="button primary" type="submit" disabled={mutation.isPending}>
            {mutation.isPending && mutation.variables?.start === true ? "Starting planning…" : "Save and start planning"}
          </button>
        </div>
      </form>
    </div>
  );
}
