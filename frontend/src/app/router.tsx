import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";

import { CreateProjectPage } from "../pages/CreateProjectPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { ProjectDetailPage } from "../pages/ProjectDetailPage";
import { ProjectsPage } from "../pages/ProjectsPage";
import { SignInPage } from "../pages/SignInPage";
import { ScenarioPage } from "../pages/ScenarioPage";
import { AdvancedExperienceRoute } from "./AdvancedRoutes";
import { AuthenticatedLayout } from "./AuthenticatedLayout";
import { RouteErrorPage } from "./RouteErrorPage";
import {
  ExecutionBoardRoute,
  ExecutionHealthRoute,
  ExecutionOverviewRoute,
  ReportDetailRoute,
  ReportsRoute,
} from "./ExecutionRoutes";
import { ClarificationsRoute, PlanningRoute, PlanReviewRoute } from "./PlanningRoutes";

export const routes: RouteObject[] = [
  {
    path: "/sign-in",
    element: <SignInPage />,
    errorElement: <RouteErrorPage />,
  },
  {
    element: <AuthenticatedLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      { path: "/", element: <Navigate to="/projects" replace /> },
      { path: "/projects", element: <ProjectsPage /> },
      { path: "/projects/new", element: <CreateProjectPage /> },
      { path: "/projects/:projectId", element: <ProjectDetailPage /> },
      { path: "/projects/:projectId/planning", element: <PlanningRoute /> },
      { path: "/projects/:projectId/clarify", element: <ClarificationsRoute /> },
      { path: "/projects/:projectId/plan/:versionId/review", element: <PlanReviewRoute /> },
      { path: "/projects/:projectId/overview", element: <ExecutionOverviewRoute /> },
      { path: "/projects/:projectId/board", element: <ExecutionBoardRoute /> },
      { path: "/projects/:projectId/health", element: <ExecutionHealthRoute /> },
      { path: "/projects/:projectId/reports", element: <ReportsRoute /> },
      { path: "/projects/:projectId/intelligence", element: <AdvancedExperienceRoute /> },
      { path: "/reports/:reportId", element: <ReportDetailRoute /> },
      { path: "/projects/:projectId/scenarios/:scenarioId", element: <ScenarioPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
