import { lazy, Suspense } from "react";

const AdvancedExperiencePage = lazy(async () => {
  const module = await import("../pages/AdvancedExperiencePage");
  return { default: module.AdvancedExperiencePage };
});

export function AdvancedExperienceRoute() {
  return (
    <Suspense
      fallback={
        <section className="content-state" aria-live="polite" aria-busy="true">
          <span className="loading-spinner" aria-hidden="true" />
          <h1>Opening full-version intelligence…</h1>
        </section>
      }
    >
      <AdvancedExperiencePage />
    </Suspense>
  );
}
