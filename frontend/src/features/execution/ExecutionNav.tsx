import { NavLink } from "react-router-dom";

export function ExecutionNav({ projectId }: { projectId: string }) {
  return (
    <nav className="execution-tabs" aria-label="Active execution views">
      <NavLink to={`/projects/${projectId}/overview`}>Overview</NavLink>
      <NavLink to={`/projects/${projectId}/board`}>Board</NavLink>
      <NavLink to={`/projects/${projectId}/health`}>Health</NavLink>
      <NavLink to={`/projects/${projectId}/reports`}>Reports</NavLink>
      <NavLink to={`/projects/${projectId}/scenarios/new`}>Scenarios</NavLink>
      <NavLink to={`/projects/${projectId}/intelligence`}>Intelligence</NavLink>
    </nav>
  );
}
