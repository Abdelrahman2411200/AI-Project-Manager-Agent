import type { TaskStatusEventView } from "../../api/types";
import { StateBadge } from "../../components/Feedback";

export function ActivityList({
  events,
  taskKeys,
}: {
  events: TaskStatusEventView[];
  taskKeys: Map<string, string>;
}) {
  return (
    <section className="execution-activity" aria-labelledby="activity-title">
      <div className="section-heading">
        <span className="eyebrow">Immutable history</span>
        <h2 id="activity-title">Recent status events</h2>
      </div>
      {events.length ? (
        <ol>
          {events.map((event) => (
            <li key={event.id}>
              <span className="activity-marker" aria-hidden="true" />
              <div>
                <div className="activity-heading">
                  <strong>{taskKeys.get(event.task_id) ?? event.task_id}</strong>
                  <StateBadge state={event.to_status} />
                </div>
                <p>{event.reason}</p>
                <small>
                  {event.actor_type === "system" ? "Calculated by system" : "Changed by owner"}
                  {" · "}
                  <time dateTime={event.occurred_at}>{new Date(event.occurred_at).toLocaleString()}</time>
                </small>
              </div>
            </li>
          ))}
        </ol>
      ) : <p>No task status events exist yet.</p>}
    </section>
  );
}
