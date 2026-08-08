import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";

import type { DependencyView, PlanGraphView, TaskView } from "../../api/types";
import { useTheme } from "../theme/themeContext";

const MAX_INTERACTIVE_NODES = 200;

export interface GraphData {
  nodes: Node[];
  edges: Edge[];
  taskById: Map<string, TaskView>;
}

function taskNode(task: TaskView, position: { x: number; y: number }): Node {
  return {
    id: task.id,
    position,
    data: {
      label: (
        <span className="graph-node-label">
          <strong>{task.stable_key}</strong>
          <span>{task.title}</span>
          <small>{task.status.replaceAll("_", " ")}</small>
        </span>
      ),
    },
    ariaLabel: `${task.stable_key}: ${task.title}. Status ${task.status.replaceAll("_", " ")}.`,
    className: `dependency-node status-${task.status}`,
  };
}

// eslint-disable-next-line react-refresh/only-export-components
export function buildDependencyGraph(plan: PlanGraphView): GraphData {
  const taskById = new Map(plan.tasks.map((task) => [task.id, task]));
  const outgoing = new Map<string, string[]>();
  const indegree = new Map(plan.tasks.map((task) => [task.id, 0]));
  const level = new Map(plan.tasks.map((task) => [task.id, 0]));
  for (const dependency of plan.dependencies) {
    outgoing.set(dependency.predecessor_id, [
      ...(outgoing.get(dependency.predecessor_id) ?? []),
      dependency.successor_id,
    ]);
    indegree.set(
      dependency.successor_id,
      (indegree.get(dependency.successor_id) ?? 0) + 1,
    );
  }
  const queue = plan.tasks
    .filter((task) => indegree.get(task.id) === 0)
    .sort((left, right) => left.stable_key.localeCompare(right.stable_key));
  for (let index = 0; index < queue.length; index += 1) {
    const current = queue[index];
    for (const successorId of outgoing.get(current.id) ?? []) {
      level.set(successorId, Math.max(level.get(successorId) ?? 0, (level.get(current.id) ?? 0) + 1));
      const remaining = (indegree.get(successorId) ?? 1) - 1;
      indegree.set(successorId, remaining);
      if (remaining === 0) {
        const successor = taskById.get(successorId);
        if (successor) queue.push(successor);
      }
    }
  }
  const rows = new Map<number, number>();
  const orderedTasks = plan.tasks
    .slice()
    .sort((left, right) => left.stable_key.localeCompare(right.stable_key));
  const edgeFreeColumns = Math.max(1, Math.ceil(Math.sqrt(orderedTasks.length)));
  const nodes: Node[] = orderedTasks.map((task, index) => {
    if (plan.dependencies.length === 0) {
      return taskNode(task, {
        x: (index % edgeFreeColumns) * 260,
        y: Math.floor(index / edgeFreeColumns) * 124,
      });
    }
    const column = level.get(task.id) ?? 0;
    const row = rows.get(column) ?? 0;
    rows.set(column, row + 1);
    return taskNode(task, { x: column * 280, y: row * 124 });
  });
  const edges: Edge[] = plan.dependencies.map((dependency) => ({
    id: dependency.id,
    source: dependency.predecessor_id,
    target: dependency.successor_id,
    label: dependency.confidence_label,
    markerEnd: { type: MarkerType.ArrowClosed },
    ariaLabel: dependencyLabel(dependency, taskById),
  }));
  return { nodes, edges, taskById };
}

function dependencyLabel(
  dependency: DependencyView,
  taskById: Map<string, TaskView>,
): string {
  const predecessor = taskById.get(dependency.predecessor_id);
  const successor = taskById.get(dependency.successor_id);
  return `${predecessor?.stable_key ?? "Unknown"} must finish before ${successor?.stable_key ?? "Unknown"}. ${dependency.reason}`;
}

export function DependencyGraph({ plan }: { plan: PlanGraphView }) {
  const graph = useMemo(() => buildDependencyGraph(plan), [plan]);
  const interactive = graph.nodes.length <= MAX_INTERACTIVE_NODES;
  const { resolvedTheme } = useTheme();

  return (
    <section className="advanced-section dependency-experience" aria-labelledby="dependency-heading">
      <div className="advanced-section-heading">
        <div>
          <span className="eyebrow">Version-local DAG</span>
          <h2 id="dependency-heading">Dependency graph</h2>
          <p>
            Direction and readiness come from the validated plan. The table contains every
            edge and remains the authoritative keyboard and screen-reader view.
          </p>
        </div>
        <span className="metric-pill">
          {plan.tasks.length} tasks · {plan.dependencies.length} edges
        </span>
      </div>

      {plan.tasks.length === 0 ? (
        <div className="empty-inline">
          <strong>No tasks to visualize</strong>
          <p>This plan version does not contain dependency nodes.</p>
        </div>
      ) : interactive ? (
        <div
          className="dependency-canvas"
          role="region"
          aria-label={`Interactive dependency overview with ${plan.tasks.length} tasks. Use the complete table below for linear navigation.`}
        >
          <ReactFlow
            nodes={graph.nodes}
            edges={graph.edges}
            colorMode={resolvedTheme}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable
            fitView
            fitViewOptions={{ padding: 0.18 }}
            minZoom={0.2}
            maxZoom={1.5}
          >
            <Background gap={20} size={1} />
            <Controls showInteractive={false} />
            {plan.tasks.length <= 75 ? <MiniMap pannable zoomable ariaLabel="Dependency minimap" /> : null}
          </ReactFlow>
        </div>
      ) : (
        <div className="feedback-banner info">
          <div>
            <strong>Large-plan table mode</strong>
            <div className="feedback-copy">
              Interactive rendering is limited to {MAX_INTERACTIVE_NODES} nodes to keep
              navigation responsive. All {plan.tasks.length} tasks remain available below.
            </div>
          </div>
        </div>
      )}

      <div className="table-scroll dependency-table" tabIndex={0}>
        <table>
          <caption>Complete dependency edge list</caption>
          <thead>
            <tr>
              <th>Predecessor</th>
              <th>Successor</th>
              <th>Reason</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {plan.dependencies.length ? (
              plan.dependencies.map((dependency) => {
                const predecessor = graph.taskById.get(dependency.predecessor_id);
                const successor = graph.taskById.get(dependency.successor_id);
                return (
                  <tr key={dependency.id}>
                    <th scope="row">
                      <code>{predecessor?.stable_key ?? "Unknown"}</code>
                      <span>{predecessor?.title}</span>
                    </th>
                    <td>
                      <code>{successor?.stable_key ?? "Unknown"}</code>
                      <span>{successor?.title}</span>
                    </td>
                    <td>{dependency.reason}</td>
                    <td>{dependency.confidence_label}</td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={4}>This plan contains no dependency edges.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
