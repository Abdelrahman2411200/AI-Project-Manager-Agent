import { NavLink } from "react-router-dom";

export function ExecutionNav({ projectId }: { projectId: string }) {
  return (
    <nav className="execution-tabs" aria-label="Active execution views">
      <NavLink to={`/projects/${projectId}/overview`}>Overview</NavLink>
      <NavLink to={`/projects/${projectId}/board`}>Board</NavLink>
      <NavLink to={`/projects/${projectId}/health`}>Health</NavLink>
    </nav>
  );
}
