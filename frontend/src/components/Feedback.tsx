import type { ReactNode } from "react";

interface FeedbackBannerProps {
  tone?: "danger" | "warning" | "success" | "info";
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}

export function FeedbackBanner({
  tone = "info",
  title,
  children,
  actions,
}: FeedbackBannerProps) {
  return (
    <section
      className={`feedback-banner ${tone}`}
      role={tone === "danger" ? "alert" : "status"}
      aria-live={tone === "danger" ? "assertive" : "polite"}
    >
      <div>
        <strong>{title}</strong>
        {children ? <div className="feedback-copy">{children}</div> : null}
      </div>
      {actions ? <div className="feedback-actions">{actions}</div> : null}
    </section>
  );
}

interface LoadingStateProps {
  title: string;
  detail?: string;
}

export function LoadingState({ title, detail }: LoadingStateProps) {
  return (
    <section className="content-state" aria-live="polite" aria-busy="true">
      <span className="loading-spinner" aria-hidden="true" />
      <h1>{title}</h1>
      {detail ? <p>{detail}</p> : null}
    </section>
  );
}

interface ErrorStateProps {
  title: string;
  detail: string;
  onRetry?: () => void;
}

export function ErrorState({ title, detail, onRetry }: ErrorStateProps) {
  return (
    <section className="content-state" role="alert">
      <span className="state-icon danger" aria-hidden="true">!</span>
      <h1>{title}</h1>
      <p>{detail}</p>
      {onRetry ? (
        <button className="button secondary" type="button" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </section>
  );
}

export function SourceBadge({
  source,
  children,
}: {
  source: "ai" | "user" | "deterministic";
  children?: ReactNode;
}) {
  return (
    <span className={`source-badge ${source}`}>
      {children ?? (source === "ai" ? "AI proposed" : source === "user" ? "Owner edited" : "Calculated")}
    </span>
  );
}

export function StateBadge({ state }: { state: string }) {
  return <span className={`state-badge ${state}`}>{state.replaceAll("_", " ")}</span>;
}
