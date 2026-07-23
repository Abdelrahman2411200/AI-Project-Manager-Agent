import type { AgentRunStepView, AgentRunView } from "../../api/types";
import { StateBadge } from "../../components/Feedback";

const publicStepNames: Record<string, string> = {
  validate_request: "Check project intake",
  detect_gaps: "Identify decisions",
  wait_or_assume: "Resolve clarifications",
  analyze_project: "Analyze project",
  identify_modules: "Shape modules",
  draft_milestones: "Draft milestones",
  draft_tasks: "Draft actionable tasks",
  generate_acceptance_criteria: "Verify acceptance criteria",
  infer_dependencies: "Validate dependencies",
  estimate_and_prioritize: "Estimate and prioritize",
  schedule: "Build the schedule",
  identify_risks: "Identify delivery risks",
  validate_plan: "Run quality checks",
  persist_draft: "Save the plan draft",
  await_approval: "Wait for owner review",
};

const statusCopy: Record<string, string> = {
  pending: "Waiting",
  queued: "Queued",
  running: "In progress",
  completed: "Complete",
  failed: "Needs attention",
  skipped: "Not needed",
  waiting: "Waiting for you",
};

function publicName(step: AgentRunStepView): string {
  return publicStepNames[step.name] ?? step.name.replaceAll("_", " ");
}

interface RunProgressProps {
  run: AgentRunView;
  steps: AgentRunStepView[];
  cancelling: boolean;
  onCancel: () => void;
}

export function RunProgress({ run, steps, cancelling, onCancel }: RunProgressProps) {
  const completed = steps.filter((step) => step.status === "completed").length;
  const progress = steps.length ? Math.round((completed / steps.length) * 100) : 0;
  const canCancel = ["queued", "running", "waiting_for_user"].includes(run.status);

  return (
    <section className="run-progress" aria-labelledby="run-progress-title">
      <div className="run-summary">
        <div>
          <span className="eyebrow">Planning run</span>
          <div className="title-with-badge">
            <h2 id="run-progress-title">
              {run.status === "waiting_for_user"
                ? "Your input is needed"
                : run.status === "completed"
                  ? "Draft plan ready"
                  : "Building your project plan"}
            </h2>
            <StateBadge state={run.status} />
          </div>
          <p>
            This view shows concise workflow outcomes only. Private model reasoning and raw
            prompts are never displayed.
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
          <span>{completed} of {steps.length || "—"} steps complete</span>
          <strong>{progress}%</strong>
        </div>
        <progress max="100" value={progress}>{progress}%</progress>
      </div>

      <ol className="run-step-list" aria-label="Planning progress">
        {steps.length ? (
          steps.map((step) => (
            <li className={`run-step ${step.status}`} key={step.id}>
              <span className="step-marker" aria-hidden="true">
                {step.status === "completed" ? "✓" : step.status === "failed" ? "!" : step.attempt}
              </span>
              <div>
                <strong>{publicName(step)}</strong>
                <span>{statusCopy[step.status] ?? step.status}</span>
              </div>
              {step.duration_ms !== null ? (
                <small>{Math.max(1, Math.round(step.duration_ms / 1000))}s</small>
              ) : null}
            </li>
          ))
        ) : (
          <li className="run-step pending">
            <span className="step-marker" aria-hidden="true">1</span>
            <div><strong>Preparing workflow</strong><span>Queued</span></div>
          </li>
        )}
      </ol>

      <dl className="run-metadata">
        <div><dt>Run reference</dt><dd>{run.id.slice(0, 8)}</dd></div>
        <div><dt>Current stage</dt><dd>{publicStepNames[run.current_step] ?? run.current_step.replaceAll("_", " ")}</dd></div>
        <div><dt>Usage</dt><dd>{run.tokens_used.toLocaleString()} / {run.token_budget.toLocaleString()} tokens</dd></div>
      </dl>
    </section>
  );
}
