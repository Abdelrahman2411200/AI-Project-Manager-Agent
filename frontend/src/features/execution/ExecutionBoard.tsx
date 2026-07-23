import { useMemo, useState } from "react";

import type {
  ExecutionBoardView,
  TaskExecutionView,
  TaskStatus,
} from "../../api/types";
import { StateBadge } from "../../components/Feedback";
import { TaskActionPanel, type TaskMutationHandlers } from "./TaskActionPanel";

const statusOrder: TaskStatus[] = [
  "pending",
  "ready",
  "in_progress",
  "blocked",
  "completed",
  "cancelled",
];

function progressLabel(task: TaskExecutionView): string {
  return `${Math.round(Number(task.progress_fraction) * 100)}%`;
}

function TaskCard({
  task,
  mutations,
  onReload,
}: {
  task: TaskExecutionView;
  mutations: TaskMutationHandlers;
  onReload: () => void;
}) {
  return (
    <article className={`execution-task-card status-${task.status}`} id={`task-${task.stable_key}`}>
      <div className="task-card-heading">
        <span className="task-key">{task.stable_key}</span>
        <StateBadge state={task.status} />
      </div>
      <h3>{task.title}</h3>
      <p>{task.deliverable}</p>
      <dl className="task-card-facts">
        <div><dt>Priority</dt><dd>{task.priority_label} · {Number(task.priority_score).toFixed(0)}</dd></div>
        <div><dt>Milestone</dt><dd>{task.milestone_key} · {task.milestone_name}</dd></div>
        <div><dt>Plan</dt><dd>{Number(task.effort_likely_hours)} h · {task.planned_finish ?? "No date"}</dd></div>
      </dl>
      <div className="task-progress-row">
        <span>Progress</span><strong>{progressLabel(task)}</strong>
        <progress max={1} value={Number(task.progress_fraction)} aria-label={`${task.stable_key} progress ${progressLabel(task)}`} />
      </div>
      {task.incomplete_predecessor_refs.length ? (
        <p className="dependency-note"><span aria-hidden="true">⏳</span> Waiting for {task.incomplete_predecessor_refs.join(", ")}</p>
      ) : null}
      {task.blocked_reason ? (
        <p className="blocker-note"><span aria-hidden="true">!</span> {task.blocked_reason}</p>
      ) : null}
      <TaskActionPanel task={task} mutations={mutations} onReload={onReload} />
    </article>
  );
}

export function ExecutionBoard({
  board,
  mutations,
  onReload,
}: {
  board: ExecutionBoardView;
  mutations: TaskMutationHandlers;
  onReload: () => void;
}) {
  const [view, setView] = useState<"board" | "list">("board");
  const [milestone, setMilestone] = useState("all");
  const [priority, setPriority] = useState("all");
  const milestones = useMemo(
    () =>
      Array.from(
        new Map(
          board.tasks.map((task) => [
            task.milestone_id,
            `${task.milestone_key} · ${task.milestone_name}`,
          ]),
        ),
      ),
    [board.tasks],
  );
  const tasks = board.tasks.filter(
    (task) =>
      (milestone === "all" || task.milestone_id === milestone) &&
      (priority === "all" || task.priority_label === priority),
  );

  return (
    <section className="execution-board-section" aria-labelledby="execution-board-title">
      <div className="section-heading split">
        <div>
          <span className="eyebrow">Active version {board.version_number}</span>
          <h2 id="execution-board-title">Task execution</h2>
          <p>Status changes wait for server confirmation and always append history.</p>
        </div>
        <div className="view-toggle" role="group" aria-label="Execution layout">
          <button type="button" aria-pressed={view === "board"} onClick={() => setView("board")}>Board</button>
          <button type="button" aria-pressed={view === "list"} onClick={() => setView("list")}>Accessible list</button>
        </div>
      </div>
      <div className="execution-filters" aria-label="Filter execution tasks">
        <label>
          Milestone
          <select value={milestone} onChange={(event) => setMilestone(event.target.value)}>
            <option value="all">All milestones</option>
            {milestones.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
        <label>
          Priority
          <select value={priority} onChange={(event) => setPriority(event.target.value)}>
            <option value="all">All priorities</option>
            {["Critical", "High", "Medium", "Low"].map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
        <span aria-live="polite">{tasks.length} task{tasks.length === 1 ? "" : "s"} shown</span>
      </div>

      {view === "board" ? (
        <div className="kanban-board">
          {statusOrder.map((status) => {
            const statusTasks = tasks.filter((task) => task.status === status);
            return (
              <section className={`kanban-column column-${status}`} key={status} aria-labelledby={`column-${status}`}>
                <header><h3 id={`column-${status}`}>{status.replaceAll("_", " ")}</h3><span>{statusTasks.length}</span></header>
                {statusTasks.length ? (
                  <div className="kanban-task-list">
                    {statusTasks.map((task) => <TaskCard key={task.task_id} task={task} mutations={mutations} onReload={onReload} />)}
                  </div>
                ) : <p className="column-empty">No tasks in this state.</p>}
              </section>
            );
          })}
        </div>
      ) : (
        <ol className="execution-list">
          {tasks.map((task) => (
            <li key={task.task_id}><TaskCard task={task} mutations={mutations} onReload={onReload} /></li>
          ))}
        </ol>
      )}
    </section>
  );
}
