import { lazy, Suspense, type ReactNode } from "react";

export const PlanningPage = lazy(async () => {
  const module = await import("../pages/PlanningPage");
  return { default: module.PlanningPage };
});

export const ClarificationsPage = lazy(async () => {
  const module = await import("../pages/ClarificationsPage");
  return { default: module.ClarificationsPage };
});

export const PlanReviewPage = lazy(async () => {
  const module = await import("../pages/PlanReviewPage");
  return { default: module.PlanReviewPage };
});

export function PlanningFallback({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <section className="content-state" aria-live="polite" aria-busy="true">
          <span className="loading-spinner" aria-hidden="true" />
          <h1>Opening planning workspace…</h1>
        </section>
      }
    >
      {children}
    </Suspense>
  );
}

export function PlanningRoute() {
  return (
    <PlanningFallback>
      <PlanningPage />
    </PlanningFallback>
  );
}

export function ClarificationsRoute() {
  return (
    <PlanningFallback>
      <ClarificationsPage />
    </PlanningFallback>
  );
}

export function PlanReviewRoute() {
  return (
    <PlanningFallback>
      <PlanReviewPage />
    </PlanningFallback>
  );
}
