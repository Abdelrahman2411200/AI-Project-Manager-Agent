import { useMemo, type CSSProperties } from "react";

import type { PlanGraphView, TaskView } from "../../api/types";

interface TimelineTask {
  task: TaskView;
  start: Date;
  finish: Date;
  startOffset: number;
  duration: number;
}

type TimelineStyle = CSSProperties & {
  "--timeline-start": number;
  "--timeline-span": number;
  "--timeline-total": number;
};

function utcDate(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}

function dayDifference(left: Date, right: Date): number {
  return Math.round((right.getTime() - left.getTime()) / 86_400_000);
}

export function ScheduleTimeline({ plan }: { plan: PlanGraphView }) {
  const schedule = useMemo(() => {
    const dated = plan.tasks.filter(
      (task): task is TaskView & { planned_start: string; planned_finish: string } =>
        Boolean(task.planned_start && task.planned_finish),
    );
    if (!dated.length) return { items: [] as TimelineTask[], start: null, finish: null, days: 0 };
    const start = new Date(
      Math.min(...dated.map((task) => utcDate(task.planned_start).getTime())),
    );
    const finish = new Date(
      Math.max(...dated.map((task) => utcDate(task.planned_finish).getTime())),
    );
    const days = Math.max(dayDifference(start, finish) + 1, 1);
    const items = dated
      .map((task) => {
        const taskStart = utcDate(task.planned_start);
        const taskFinish = utcDate(task.planned_finish);
        return {
          task,
          start: taskStart,
          finish: taskFinish,
          startOffset: dayDifference(start, taskStart),
          duration: Math.max(dayDifference(taskStart, taskFinish) + 1, 1),
        };
      })
      .sort(
        (left, right) =>
          left.start.getTime() - right.start.getTime() ||
          left.task.stable_key.localeCompare(right.task.stable_key),
      );
    return { items, start, finish, days };
  }, [plan.tasks]);
  const milestoneById = new Map(plan.milestones.map((item) => [item.id, item]));
  const unscheduled = plan.tasks.filter(
    (task) => !task.planned_start || !task.planned_finish,
  );

  return (
    <section className="advanced-section timeline-experience" aria-labelledby="timeline-heading">
      <div className="advanced-section-heading">
        <div>
          <span className="eyebrow">Persisted schedule</span>
          <h2 id="timeline-heading">Timeline and Gantt</h2>
          <p>
            Bars display date-only planned work. Text labels and the complete table convey
            the same information without relying on position or color.
          </p>
        </div>
        {schedule.start && schedule.finish ? (
          <span className="metric-pill">
            {schedule.start.toISOString().slice(0, 10)} →{" "}
            {schedule.finish.toISOString().slice(0, 10)}
          </span>
        ) : null}
      </div>

      {schedule.items.length ? (
        <div className="timeline-scroll" tabIndex={0}>
          <div
            className="timeline-grid"
            role="img"
            aria-label={`Planned schedule from ${schedule.start?.toISOString().slice(0, 10)} through ${schedule.finish?.toISOString().slice(0, 10)} with ${schedule.items.length} scheduled tasks.`}
          >
            {schedule.items.map((item) => {
              const style: TimelineStyle = {
                "--timeline-start": item.startOffset,
                "--timeline-span": item.duration,
                "--timeline-total": schedule.days,
              };
              return (
                <div className="timeline-row" key={item.task.id}>
                  <div className="timeline-label">
                    <code>{item.task.stable_key}</code>
                    <span>{item.task.title}</span>
                  </div>
                  <div className="timeline-track">
                    <span
                      className={`timeline-bar status-${item.task.status}`}
                      style={style}
                      aria-label={`${item.task.stable_key}, ${item.task.planned_start} through ${item.task.planned_finish}, ${item.duration} days, status ${item.task.status.replaceAll("_", " ")}`}
                    >
                      {item.duration}d
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="empty-inline">
          <strong>No calculated dates</strong>
          <p>Validate the draft or activate a scheduled plan to populate the timeline.</p>
        </div>
      )}

      <div className="table-scroll" tabIndex={0}>
        <table>
          <caption>Complete planned schedule</caption>
          <thead>
            <tr>
              <th>Task</th>
              <th>Milestone</th>
              <th>Start</th>
              <th>Finish</th>
              <th>Likely effort</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {plan.tasks.map((task) => (
              <tr key={task.id}>
                <th scope="row">
                  <code>{task.stable_key}</code>
                  <span>{task.title}</span>
                </th>
                <td>{milestoneById.get(task.milestone_id)?.name ?? "Unknown milestone"}</td>
                <td>{task.planned_start ?? "Not scheduled"}</td>
                <td>{task.planned_finish ?? "Not scheduled"}</td>
                <td>{task.effort_likely_hours} hours</td>
                <td>{task.status.replaceAll("_", " ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {unscheduled.length ? (
        <p className="advanced-note">
          {unscheduled.length} task{unscheduled.length === 1 ? " is" : "s are"} not scheduled
          and therefore appear only in the table.
        </p>
      ) : null}
    </section>
  );
}
