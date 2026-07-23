import { useQuery } from "@tanstack/react-query";
import { Navigate, useLocation } from "react-router-dom";

import { getCurrentSession } from "../api/auth";
import { ApiError } from "../api/client";
import { RootLayout } from "./RootLayout";

export function AuthenticatedLayout() {
  const location = useLocation();
  const session = useQuery({
    queryKey: ["session"],
    queryFn: getCurrentSession,
    retry: false,
  });

  if (session.isPending) {
    return (
      <main className="route-state" aria-live="polite">
        <span className="loading-spinner" aria-hidden="true" />
        <h1>Opening your workspace…</h1>
      </main>
    );
  }

  if (session.error instanceof ApiError && session.error.problem.status === 401) {
    return <Navigate to="/sign-in" replace state={{ from: location.pathname }} />;
  }

  if (session.isError) {
    return (
      <main className="route-state" role="alert">
        <span className="eyebrow">Connection problem</span>
        <h1>We could not verify your session.</h1>
        <button type="button" className="button secondary" onClick={() => void session.refetch()}>
          Try again
        </button>
      </main>
    );
  }

  return <RootLayout user={session.data.user} />;
}
