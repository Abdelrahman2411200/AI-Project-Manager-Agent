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

export const ReportsPage = lazy(async () => {
  const module = await import("../pages/ReportsPage");
  return { default: module.ReportsPage };
});

export const ReportDetailPage = lazy(async () => {
  const module = await import("../pages/ReportDetailPage");
  return { default: module.ReportDetailPage };
});

export const MyTasksPage = lazy(async () => {
  const module = await import("../pages/MyTasksPage");
  return { default: module.MyTasksPage };
});

export const ReportsIndexPage = lazy(async () => {
  const module = await import("../pages/ReportsIndexPage");
  return { default: module.ReportsIndexPage };
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

export function ReportsRoute() {
  return <ExecutionFallback><ReportsPage /></ExecutionFallback>;
}

export function ReportDetailRoute() {
  return <ExecutionFallback><ReportDetailPage /></ExecutionFallback>;
}

export function MyTasksRoute() {
  return <ExecutionFallback><MyTasksPage /></ExecutionFallback>;
}

export function ReportsIndexRoute() {
  return <ExecutionFallback><ReportsIndexPage /></ExecutionFallback>;
}

export function ExecutionFallback({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<section className="content-state" aria-live="polite" aria-busy="true"><span className="loading-spinner" aria-hidden="true" /><h1>Opening active execution…</h1></section>}>
      {children}
    </Suspense>
  );
}
