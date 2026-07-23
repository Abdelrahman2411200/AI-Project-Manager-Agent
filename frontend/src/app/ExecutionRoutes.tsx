import { lazy, Suspense, type ReactNode } from "react";

export const ExecutionBoardPage = lazy(async () => {
  const module = await import("../pages/ExecutionBoardPage");
  return { default: module.ExecutionBoardPage };
});

export const ExecutionOverviewPage = lazy(async () => {
  const module = await import("../pages/ExecutionOverviewPage");
  return { default: module.ExecutionOverviewPage };
});

export const ExecutionHealthPage = lazy(async () => {
  const module = await import("../pages/ExecutionHealthPage");
  return { default: module.ExecutionHealthPage };
});

export function ExecutionBoardRoute() {
  return <ExecutionFallback><ExecutionBoardPage /></ExecutionFallback>;
}

export function ExecutionOverviewRoute() {
  return <ExecutionFallback><ExecutionOverviewPage /></ExecutionFallback>;
}

export function ExecutionHealthRoute() {
  return <ExecutionFallback><ExecutionHealthPage /></ExecutionFallback>;
}

export function ExecutionFallback({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<section className="content-state" aria-live="polite" aria-busy="true"><span className="loading-spinner" aria-hidden="true" /><h1>Opening active execution…</h1></section>}>
      {children}
    </Suspense>
  );
}
