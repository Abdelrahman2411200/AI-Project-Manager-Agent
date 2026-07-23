import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { errorMessage, isConflict } from "../../api/errorUtils";
import type { TaskExecutionView, TaskStatus } from "../../api/types";
import { FeedbackBanner } from "../../components/Feedback";

const reasonSchema = z.object({
  reason: z.string().trim().min(3, "Enter at least 3 characters.").max(1000),
});
const progressSchema = z.object({
  percent: z.number().min(0).max(99),
  actualEffortHours: z.number().min(0).max(1_000_000),
  note: z.string().max(2000),
});

type ReasonValues = z.infer<typeof reasonSchema>;
type ProgressValues = z.infer<typeof progressSchema>;

export interface TaskMutationHandlers {
  status: {
    mutateAsync: (input: {
      taskId: string;
      rowVersion: number;
      toStatus: TaskStatus;
      reason?: string;
    }) => Promise<unknown>;
    isPending: boolean;
    error: unknown;
    reset: () => void;
  };
  progress: {
    mutateAsync: (input: {
      taskId: string;
      rowVersion: number;
      fraction: number;
      actualEffortHours: number;
      note?: string;
    }) => Promise<unknown>;
    isPending: boolean;
    error: unknown;
    reset: () => void;
  };
}

export function TaskActionPanel({
  task,
  mutations,
  onReload,
}: {
  task: TaskExecutionView;
  mutations: TaskMutationHandlers;
  onReload: () => void;
}) {
  const [action, setAction] = useState<TaskStatus | "progress" | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const reasonForm = useForm<ReasonValues>({
    resolver: zodResolver(reasonSchema),
    defaultValues: { reason: "" },
  });
  const progressForm = useForm<ProgressValues>({
    resolver: zodResolver(progressSchema),
    defaultValues: {
      percent: Math.round(Number(task.progress_fraction) * 100),
      actualEffortHours: Number(task.actual_effort_hours),
      note: "",
    },
  });
  useEffect(() => {
    if (action) panelRef.current?.focus();
  }, [action]);

  const pending = mutations.status.isPending || mutations.progress.isPending;
  const conflict = isConflict(mutations.status.error) || isConflict(mutations.progress.error);
  const close = () => {
    setAction(null);
    reasonForm.reset();
    mutations.status.reset();
    mutations.progress.reset();
  };
  const runStatus = async (toStatus: TaskStatus, reason?: string) => {
    try {
      await mutations.status.mutateAsync({
        taskId: task.task_id,
        rowVersion: task.row_version,
        toStatus,
        reason,
      });
      close();
    } catch {
      // TanStack Query owns and renders the typed mutation error.
    }
  };
  const runProgress = async (values: ProgressValues) => {
    try {
      await mutations.progress.mutateAsync({
        taskId: task.task_id,
        rowVersion: task.row_version,
        fraction: values.percent / 100,
        actualEffortHours: values.actualEffortHours,
        note: values.note || undefined,
      });
      close();
    } catch {
      // TanStack Query owns and renders the typed mutation error.
    }
  };
  const directActions: Array<{ status: TaskStatus; label: string }> = [];
  if (task.status === "ready") directActions.push({ status: "in_progress", label: "Start task" });
  if (task.status === "blocked") directActions.push({ status: "in_progress", label: "Resume task" });
  if (task.status === "in_progress") directActions.push({ status: "completed", label: "Complete task" });

  if (!action) {
    return (
      <div className="task-actions" aria-label={`Actions for ${task.stable_key}`}>
        {directActions.map((item) => (
          <button
            key={item.status}
            type="button"
            className="button compact primary"
            onClick={() => setAction(item.status)}
          >
            {item.label}
          </button>
        ))}
        {["in_progress", "blocked"].includes(task.status) ? (
          <button type="button" className="button compact secondary" onClick={() => setAction("progress")}>
            Update progress
          </button>
        ) : null}
        {["ready", "in_progress"].includes(task.status) ? (
          <button type="button" className="button compact secondary" onClick={() => setAction("blocked")}>
            Block
          </button>
        ) : null}
        {!["completed", "cancelled"].includes(task.status) ? (
          <button type="button" className="text-button danger-text" onClick={() => setAction("cancelled")}>
            Cancel
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div
      className="task-action-panel"
      role="dialog"
      aria-label={`${action === "progress" ? "Update progress" : "Confirm status change"} for ${task.stable_key}`}
      tabIndex={-1}
      ref={panelRef}
    >
      {conflict ? (
        <FeedbackBanner
          tone="warning"
          title="This task changed in another session"
          actions={<button type="button" className="button compact secondary" onClick={onReload}>Load latest task</button>}
        >
          Your update was not applied. Reload the current execution state and try again.
        </FeedbackBanner>
      ) : mutations.status.error || mutations.progress.error ? (
        <FeedbackBanner tone="danger" title="The task could not be updated">
          {errorMessage(mutations.status.error ?? mutations.progress.error, "Try again or reload the execution board.")}
        </FeedbackBanner>
      ) : null}

      {action === "blocked" || action === "cancelled" ? (
        <form
          onSubmit={(event) => {
            void reasonForm.handleSubmit(({ reason }) => {
              void runStatus(action, reason);
            })(event);
          }}
        >
          <strong>{action === "blocked" ? "Record the blocker" : "Cancel this task"}</strong>
          <label htmlFor={`reason-${task.task_id}`}>Reason *</label>
          <textarea
            id={`reason-${task.task_id}`}
            rows={3}
            {...reasonForm.register("reason")}
            aria-invalid={Boolean(reasonForm.formState.errors.reason)}
          />
          {reasonForm.formState.errors.reason ? <p className="field-error">{reasonForm.formState.errors.reason.message}</p> : null}
          <div className="task-action-buttons">
            <button className="button compact primary" type="submit" disabled={pending}>
              {pending ? "Saving…" : action === "blocked" ? "Confirm blocker" : "Confirm cancellation"}
            </button>
            <button className="button compact secondary" type="button" onClick={close} disabled={pending}>Go back</button>
          </div>
        </form>
      ) : action === "progress" ? (
        <form
          onSubmit={(event) => {
            void progressForm.handleSubmit((values) => {
              void runProgress(values);
            })(event);
          }}
        >
          <strong>Update factual progress</strong>
          <div className="form-grid two-column">
            <div className="field-group">
              <label htmlFor={`percent-${task.task_id}`}>Completion percent</label>
              <input id={`percent-${task.task_id}`} type="number" min="0" max="99" {...progressForm.register("percent", { valueAsNumber: true })} />
              {progressForm.formState.errors.percent ? <p className="field-error">{progressForm.formState.errors.percent.message}</p> : null}
            </div>
            <div className="field-group">
              <label htmlFor={`effort-${task.task_id}`}>Actual effort hours</label>
              <input id={`effort-${task.task_id}`} type="number" min="0" step="0.25" {...progressForm.register("actualEffortHours", { valueAsNumber: true })} />
              {progressForm.formState.errors.actualEffortHours ? <p className="field-error">{progressForm.formState.errors.actualEffortHours.message}</p> : null}
            </div>
          </div>
          <label htmlFor={`note-${task.task_id}`}>Progress note</label>
          <textarea id={`note-${task.task_id}`} rows={2} {...progressForm.register("note")} />
          <div className="task-action-buttons">
            <button className="button compact primary" type="submit" disabled={pending}>{pending ? "Saving…" : "Save progress"}</button>
            <button className="button compact secondary" type="button" onClick={close} disabled={pending}>Go back</button>
          </div>
        </form>
      ) : (
        <div>
          <strong>
            {action === "completed"
              ? "Mark this task complete?"
              : action === "in_progress"
                ? task.status === "blocked" ? "Resume this task?" : "Start this task?"
                : `Move task to ${action.replaceAll("_", " ")}?`}
          </strong>
          <p>The server will record an immutable status event and recalculate downstream readiness, progress, forecast, and health.</p>
          <div className="task-action-buttons">
            <button className="button compact primary" type="button" disabled={pending} onClick={() => void runStatus(action)}>
              {pending ? "Saving…" : "Confirm change"}
            </button>
            <button className="button compact secondary" type="button" onClick={close} disabled={pending}>Go back</button>
          </div>
        </div>
      )}
    </div>
  );
}
