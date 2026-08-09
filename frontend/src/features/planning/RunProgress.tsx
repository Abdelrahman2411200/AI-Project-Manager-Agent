import { useEffect, useMemo, useState } from "react";

import type { AgentRunStepView, AgentRunView } from "../../api/types";
import { StateBadge } from "../../components/Feedback";

const publicStepNames: Record<string, string> = {
  validate_request: "Check project intake",
  detect_gaps: "Identify decisions",
  wait_or_assume: "Resolve clarifications",
  analyze_project: "Analyze project",
  draft_modules: "Shape project modules",
  identify_modules: "Shape modules",
  draft_milestones: "Draft milestones",
  draft_tasks: "Draft actionable tasks",
  strengthen_acceptance: "Strengthen acceptance criteria",
  generate_acceptance_criteria: "Verify acceptance criteria",
  suggest_dependencies: "Suggest dependencies",
  infer_dependencies: "Validate dependencies",
  validate_graph: "Validate dependency graph",
  normalize_effort: "Normalize task effort",
  score_priority: "Score task priorities",
  estimate_and_prioritize: "Estimate and prioritize",
  schedule: "Build the schedule",
  identify_risks: "Identify delivery risks",
  quality_gate: "Run quality gate",
  validate_plan: "Run quality checks",
  persist_draft: "Save the plan draft",
  await_approval: "Prepare owner review",
  "plan.clarify": "Resolve clarifications",
  "plan.analyze": "Analyze project",
  "plan.modules": "Shape project modules",
  "plan.milestones": "Draft milestones",
  "plan.tasks": "Draft actionable tasks",
  "plan.dependencies": "Validate dependencies",
  "plan.estimates": "Estimate and prioritize",
  "plan.schedule": "Build the schedule",
  "plan.risks": "Identify delivery risks",
  "plan.persist_draft": "Save the plan draft",
};

const allNodeNames = [
  "validate_request",
  "detect_gaps",
  "wait_or_assume",
  "analyze_project",
  "draft_modules",
  "draft_milestones",
  "draft_tasks",
  "strengthen_acceptance",
  "suggest_dependencies",
  "validate_graph",
  "normalize_effort",
  "score_priority",
  "schedule",
  "identify_risks",
  "quality_gate",
  "persist_draft",
  "await_approval",
] as const;

interface WorkflowStepDefinition {
  id: string;
  label: string;
  description: string;
  nodeNames: readonly string[];
  completionNode: string;
}

const workflowSteps: WorkflowStepDefinition[] = [
  {
    id: "intake",
    label: "Check project intake",
    description: "Normalize and verify the project facts supplied by the owner.",
    nodeNames: ["validate_request"],
    completionNode: "validate_request",
  },
  {
    id: "decisions",
    label: "Identify decisions",
    description: "Find material decisions that must be confirmed before planning.",
    nodeNames: ["detect_gaps"],
    completionNode: "detect_gaps",
  },
  {
    id: "clarifications",
    label: "Resolve clarifications",
    description: "Apply owner answers and keep every assumption explicit.",
    nodeNames: ["wait_or_assume"],
    completionNode: "wait_or_assume",
  },
  {
    id: "analysis",
    label: "Analyze project",
    description: "Turn confirmed project facts into a grounded delivery analysis.",
    nodeNames: ["analyze_project"],
    completionNode: "analyze_project",
  },
  {
    id: "modules",
    label: "Shape project modules",
    description: "Organize the requested scope into coherent project modules.",
    nodeNames: ["draft_modules"],
    completionNode: "draft_modules",
  },
  {
    id: "milestones",
    label: "Draft milestones",
    description: "Create ordered, outcome-focused delivery milestones.",
    nodeNames: ["draft_milestones"],
    completionNode: "draft_milestones",
  },
  {
    id: "tasks",
    label: "Draft actionable tasks",
    description: "Build, schedule, validate, and safely persist the complete plan draft.",
    nodeNames: [
      "draft_tasks",
      "strengthen_acceptance",
      "suggest_dependencies",
      "validate_graph",
      "normalize_effort",
      "score_priority",
      "schedule",
      "identify_risks",
      "quality_gate",
      "persist_draft",
      "await_approval",
    ],
    completionNode: "await_approval",
  },
];

type WorkflowStepStatus =
  | "pending"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "skipped"
  | "waiting";

const statusCopy: Record<WorkflowStepStatus, string> = {
  pending: "Pending",
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  skipped: "Skipped",
  waiting: "Waiting for you",
};

const liveActivityCopy: Record<string, string> = {
  validate_request: "Checking dates, capacity, scope, and persisted project facts.",
  detect_gaps: "Identifying only the decisions that materially affect the plan.",
  wait_or_assume: "Applying confirmed answers and explicitly accepted assumptions.",
  analyze_project: "Building a grounded analysis from confirmed project context.",
  draft_modules: "Organizing requirements into clear, requirement-covered modules.",
  draft_milestones: "Sequencing milestone outcomes against the delivery constraints.",
  draft_tasks: "Creating actionable, estimable tasks for every milestone.",
  strengthen_acceptance: "Making task completion criteria observable and testable.",
  suggest_dependencies: "Finding evidence-backed finish-to-start dependencies.",
  validate_graph: "Checking task references and proving the dependency graph is acyclic.",
  normalize_effort: "Normalizing task effort ranges for deterministic calculations.",
  score_priority: "Calculating explainable task priorities outside the model.",
  schedule: "Building a capacity- and dependency-aware delivery schedule.",
  identify_risks: "Identifying grounded project and schedule risks.",
  quality_gate: "Verifying coverage, specificity, scope, schedule, and assumptions.",
  persist_draft: "Saving the validated plan graph in one atomic operation.",
  await_approval: "Preparing the validated draft for explicit owner review.",
};

interface ValidationDetail {
  code: string | null;
  message: string;
  references: string[];
}

interface DisplayWorkflowStep extends WorkflowStepDefinition {
  status: WorkflowStepStatus;
  rawSteps: AgentRunStepView[];
  durationMs: number | null;
  validation: ValidationDetail[];
}

function publicName(name: string): string {
  return publicStepNames[name] ?? name.replaceAll("_", " ");
}

function validationDetails(step: AgentRunStepView): ValidationDetail[] {
  return step.validation.flatMap((raw) => {
    const message = typeof raw.message === "string" ? raw.message : null;
    if (!message) return [];
    return [{
      code: typeof raw.code === "string" ? raw.code : null,
      message,
      references: Array.isArray(raw.references)
        ? raw.references.filter(
            (reference): reference is string => typeof reference === "string",
          )
        : [],
    }];
  });
}

function nodeIndex(name: string): number {
  return allNodeNames.indexOf(name as (typeof allNodeNames)[number]);
}

function workflowStatus(
  definition: WorkflowStepDefinition,
  run: AgentRunView,
  rawSteps: AgentRunStepView[],
): WorkflowStepStatus {
  if (run.status === "completed") return "completed";
  const completion = rawSteps.find(
    (step) => step.name === definition.completionNode && step.status === "completed",
  );
  if (completion) return "completed";

  const currentIsHere = definition.nodeNames.includes(run.current_step);
  const failed = rawSteps.some((step) => step.status === "failed");
  if (currentIsHere && (run.status === "failed" || run.status === "partial")) {
    return "failed";
  }
  if (currentIsHere && run.status === "cancelled") return "cancelled";
  if (currentIsHere && run.status === "waiting_for_user") return "waiting";
  if (currentIsHere && run.status === "queued") return "queued";
  if (currentIsHere && run.status === "running") return "running";
  if (rawSteps.some((step) => step.status === "running")) return "running";
  if (failed && currentIsHere) return "failed";
  if (rawSteps.length && rawSteps.every((step) => step.status === "skipped")) return "skipped";

  const currentIndex = nodeIndex(run.current_step);
  const endIndex = Math.max(...definition.nodeNames.map(nodeIndex));
  if (currentIndex > endIndex) return "completed";
  if (run.status === "cancelled" && currentIndex < 0 && definition.id === "intake") {
    return "cancelled";
  }
  return "pending";
}

function parseTime(value: string | null): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function formatDuration(durationMs: number | null): string {
  if (durationMs === null) return "Not started";
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1_000));
  if (totalSeconds < 60) return `${Math.max(1, totalSeconds)}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

function formatStarted(value: string | null): string {
  if (!value) return "Not started";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function stepDuration(rawSteps: AgentRunStepView[], now: number): number | null {
  if (!rawSteps.length) return null;
  return rawSteps.reduce((total, step) => {
    if (step.duration_ms !== null) return total + step.duration_ms;
    const started = parseTime(step.started_at);
    return started === null ? total : total + Math.max(0, now - started);
  }, 0);
}

function activityDuration(step: AgentRunStepView, now: number): string {
  if (step.duration_ms !== null) return formatDuration(step.duration_ms);
  const started = parseTime(step.started_at);
  return formatDuration(started === null ? null : Math.max(0, now - started));
}

function useLiveNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

function StepIcon({ status, index }: { status: WorkflowStepStatus; index: number }) {
  if (status === "completed") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path d="m5 10 3 3 7-7" />
      </svg>
    );
  }
  if (status === "failed") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path d="M6 6l8 8M14 6l-8 8" />
      </svg>
    );
  }
  if (status === "cancelled" || status === "skipped") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path d="M5 10h10" />
      </svg>
    );
  }
  if (status === "running") {
    return <span className="run-step-spinner" aria-hidden="true" />;
  }
  return <span aria-hidden="true">{index + 1}</span>;
}

function activityState(step: AgentRunStepView): string {
  if (step.status === "completed") return "Completed";
  if (step.status === "running") return "Working now";
  if (step.status === "failed") return step.retryable ? "Retrying safely" : "Stopped";
  if (step.status === "cancelled") return "Cancelled";
  return "Skipped";
}

interface RunProgressProps {
  run: AgentRunView;
  steps: AgentRunStepView[];
  cancelling: boolean;
  onCancel: () => void;
}

export function RunProgress({ run, steps, cancelling, onCancel }: RunProgressProps) {
  const isLive = ["queued", "running", "waiting_for_user"].includes(run.status);
  const now = useLiveNow(isLive);
  const displaySteps = useMemo<DisplayWorkflowStep[]>(
    () => {
      const calculated = workflowSteps.map((definition) => {
        const rawSteps = steps
          .filter((step) => definition.nodeNames.includes(step.name))
          .sort((left, right) =>
            Date.parse(left.started_at) - Date.parse(right.started_at) || left.attempt - right.attempt,
          );
        return {
          ...definition,
          rawSteps,
          status: workflowStatus(definition, run, rawSteps),
          durationMs: stepDuration(rawSteps, now),
          validation: rawSteps.flatMap(validationDetails),
        };
      });
      if (run.status === "cancelled" && !calculated.some((step) => step.status === "cancelled")) {
        const interrupted = calculated.find(
          (step) => !["completed", "skipped"].includes(step.status),
        );
        if (interrupted) interrupted.status = "cancelled";
      }
      return calculated;
    },
    [now, run, steps],
  );
  const completed = displaySteps.filter((step) => step.status === "completed").length;
  const progress = Math.round((completed / displaySteps.length) * 100);
  const canCancel = ["queued", "running", "waiting_for_user"].includes(run.status);
  const runStarted = parseTime(run.started_at);
  const runEnded = parseTime(run.completed_at);
  const elapsed = runStarted === null
    ? null
    : Math.max(0, (runEnded ?? now) - runStarted);
  const activeStep = displaySteps.find((step) =>
    ["queued", "running", "waiting", "failed", "cancelled"].includes(step.status),
  );
  const currentActivity = run.status === "cancelled" && activeStep
    ? activeStep.label
    : publicName(run.current_step);

  return (
    <section className="run-progress" aria-labelledby="run-progress-title">
      <p className="sr-only" role="status" aria-live="polite">
        Planning run {run.status.replaceAll("_", " ")}. Current stage: {currentActivity}.
        {completed} of {displaySteps.length} steps complete.
      </p>

      <div className="run-summary">
        <div>
          <span className="eyebrow">Planning run</span>
          <div className="title-with-badge">
            <h2 id="run-progress-title">
              {run.status === "waiting_for_user"
                ? "Your input is needed"
                : run.status === "completed"
                  ? "Draft plan ready"
                  : run.status === "failed" || run.status === "partial"
                    ? "Planning stopped safely"
                    : run.status === "cancelled"
                      ? "Planning run cancelled"
                      : "Building your project plan"}
            </h2>
            <StateBadge state={run.status} />
          </div>
          <p>
            Follow each planning stage as it changes. Only safe workflow activity is shown;
            private reasoning and raw prompts are never displayed.
          </p>
        </div>
        {canCancel ? (
          <button
            className="button secondary"
            type="button"
            disabled={cancelling || run.cancel_requested}
            onClick={onCancel}
          >
            {cancelling || run.cancel_requested ? "Cancelling…" : "Cancel run"}
          </button>
        ) : null}
      </div>

      <div className="progress-meter">
        <div className="progress-copy">
          <span>{completed} of {displaySteps.length} steps complete</span>
          <span className="progress-elapsed">Elapsed {formatDuration(elapsed)}</span>
          <strong>{progress}%</strong>
        </div>
        <progress aria-label="Overall planning progress" max="100" value={progress}>
          {progress}%
        </progress>
      </div>

      <div className="run-workflow-heading">
        <div>
          <span className="eyebrow">Workflow steps</span>
          <h3>Planning activity</h3>
        </div>
        {isLive ? (
          <span className="live-indicator"><span aria-hidden="true" /> Live updates</span>
        ) : null}
      </div>

      <ol className="run-step-list" aria-label="Planning progress">
        {displaySteps.map((step, index) => {
          const expanded = step.id === activeStep?.id;
          const activity = step.rawSteps.slice(-4);
          return (
            <li
              className={`run-step ${step.status}${expanded ? " expanded" : ""}`}
              key={step.id}
              aria-current={expanded ? "step" : undefined}
            >
              <span className="step-marker" aria-hidden="true">
                <StepIcon status={step.status} index={index} />
              </span>
              <div className="run-step-content">
                <div className="run-step-heading">
                  <div>
                    <strong>{step.label}</strong>
                    <span className="run-step-state">
                      {statusCopy[step.status]}
                      {step.durationMs !== null ? ` · ${formatDuration(step.durationMs)}` : ""}
                    </span>
                  </div>
                  {step.status === "running" ? <span className="running-pill">In progress</span> : null}
                </div>
                {expanded ? (
                  <div className="run-step-activity" aria-label={`${step.label} activity`}>
                    <div className="activity-summary">
                      <span className={`activity-dot ${step.status}`} aria-hidden="true" />
                      <div>
                        <strong>{currentActivity}</strong>
                        <p>
                          {run.status === "waiting_for_user"
                            ? "The workflow is paused at a protected decision checkpoint and will resume after your answers are saved."
                            : run.status === "queued"
                              ? "The durable run is ready and waiting for the planning worker to begin this stage."
                              : run.status === "cancelled"
                                ? "The cancellation was saved and no additional planning work will start."
                                : liveActivityCopy[run.current_step] ?? step.description}
                        </p>
                      </div>
                    </div>
                    {activity.length ? (
                      <ol className="activity-feed" aria-label="Recent stage activity">
                        {activity.map((rawStep) => (
                          <li key={rawStep.id}>
                            <span>{publicName(rawStep.name)}</span>
                            <small>{activityState(rawStep)} · {activityDuration(rawStep, now)}</small>
                          </li>
                        ))}
                      </ol>
                    ) : null}
                    {step.validation.length ? (
                      <ul
                        className="run-step-validation"
                        aria-label={`${step.label} validation details`}
                      >
                        {step.validation.map((issue, validationIndex) => (
                          <li key={`${issue.code ?? "validation"}-${validationIndex}`}>
                            <span>{issue.message}</span>
                            {issue.references.length ? (
                              <code>{issue.references.join(", ")}</code>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>

      <div className="run-information-heading">
        <span className="eyebrow">Run information</span>
      </div>
      <dl className="run-metadata run-metadata-expanded">
        <div><dt>Run reference</dt><dd><code>{run.id.slice(0, 8)}</code></dd></div>
        <div><dt>Current stage</dt><dd>{currentActivity}</dd></div>
        <div><dt>Started</dt><dd>{formatStarted(run.started_at)}</dd></div>
        <div><dt>Elapsed</dt><dd>{formatDuration(elapsed)}</dd></div>
        <div><dt>Usage</dt><dd>{run.tokens_used.toLocaleString()} / {run.token_budget.toLocaleString()} tokens</dd></div>
      </dl>
    </section>
  );
}
