import { isRouteErrorResponse, useRouteError } from "react-router-dom";

function isChunkLoadError(error: unknown): boolean {
  const message =
    error instanceof Error
      ? `${error.name}: ${error.message}`
      : typeof error === "string"
        ? error
        : "";
  return /dynamically imported module|loading chunk|module script failed/i.test(message);
}

export function RouteErrorPage() {
  const error = useRouteError();
  const deploymentChanged = isChunkLoadError(error);
  const routeStatus = isRouteErrorResponse(error) ? error.status : null;

  return (
    <main className="fatal-error" role="alert">
      <span className="eyebrow">
        {deploymentChanged ? "Application update detected" : "Unexpected error"}
      </span>
      <h1>
        {deploymentChanged
          ? "Reload the latest workspace version"
          : "The workspace could not be displayed"}
      </h1>
      <p>
        {deploymentChanged
          ? "The application changed while this tab was open. Reload to continue with the latest version; your persisted project data is safe."
          : routeStatus === 404
            ? "This page is not available. Return to your projects and choose another destination."
            : "The page stopped safely before changing project data. Reload the workspace or return to your projects."}
      </p>
      <div className="header-actions">
        <button className="button primary" type="button" onClick={() => window.location.reload()}>
          Reload latest version
        </button>
        <a className="button secondary" href="/projects">
          Return to projects
        </a>
      </div>
    </main>
  );
}
