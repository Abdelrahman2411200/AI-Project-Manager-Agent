import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getPlanVersion, listPlanVersions, planKeys } from "../api/plans";
import { getProject, projectKeys } from "../api/projects";
import { errorMessage, isPermissionError } from "../api/errorUtils";
import { ErrorState, LoadingState } from "../components/Feedback";
import { PlanReview } from "../features/plans/PlanReview";

export function PlanReviewPage() {
  const { projectId = "", versionId = "" } = useParams();
  const project = useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId),
    retry: (failureCount, error) => !isPermissionError(error) && failureCount < 1,
  });
  const plan = useQuery({
    queryKey: planKeys.detail(versionId),
    queryFn: () => getPlanVersion(versionId),
    enabled: Boolean(versionId),
    staleTime: 0,
    retry: (failureCount, error) => !isPermissionError(error) && failureCount < 1,
  });
  const versions = useQuery({
    queryKey: planKeys.project(projectId),
    queryFn: () => listPlanVersions(projectId),
    enabled: Boolean(projectId),
  });

  if (project.isPending || plan.isPending) {
    return <LoadingState title="Loading plan review…" detail="Opening the exact persisted plan version." />;
  }
  const queryError = project.error ?? plan.error;
  if (queryError) {
    return (
      <ErrorState
        title={isPermissionError(queryError) ? "Plan review unavailable" : "Plan could not be loaded"}
        detail={
          isPermissionError(queryError)
            ? "This plan does not exist, or your account does not have permission to review it."
            : errorMessage(queryError, "Try loading the plan again.")
        }
        onRetry={() => {
          void project.refetch();
          void plan.refetch();
        }}
      />
    );
  }
  if (!project.data || !plan.data) return null;
  const refresh = async () => {
    await plan.refetch();
    await versions.refetch();
  };

  return (
    <div className="page-stack plan-review-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to="/projects">Projects</Link><span aria-hidden="true">/</span>
        <Link to={`/projects/${projectId}`}>{project.data.name}</Link><span aria-hidden="true">/</span>
        <span aria-current="page">Review version {plan.data.number}</span>
      </nav>
      <header className="page-header review-page-header">
        <div>
          <span className="eyebrow">Human approval boundary</span>
          <h1>Review the complete project plan</h1>
          <p>Inspect provenance, edit owner-controlled content, resolve deterministic validation issues, and approve only the exact reviewed version.</p>
        </div>
        {versions.data && versions.data.length > 1 ? (
          <label className="version-picker">
            <span>Plan history</span>
            <select
              value={versionId}
              onChange={(event) => {
                window.location.assign(`/projects/${projectId}/plan/${event.target.value}/review`);
              }}
            >
              {versions.data.map((version) => (
                <option key={version.id} value={version.id}>
                  Version {version.number} · {version.state.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </header>
      <div className="review-legend" aria-label="Content provenance legend">
        <span><i className="legend-dot ai" /> AI proposed</span>
        <span><i className="legend-dot user" /> Owner edited</span>
        <span><i className="legend-dot deterministic" /> Deterministically calculated</span>
      </div>
      <PlanReview project={project.data} plan={plan.data} onRefresh={refresh} />
    </div>
  );
}
