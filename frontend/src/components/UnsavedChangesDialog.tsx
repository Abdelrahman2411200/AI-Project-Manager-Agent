import type { useUnsavedChanges } from "../hooks/useUnsavedChanges";

export function UnsavedChangesDialog({
  blocker,
}: {
  blocker: ReturnType<typeof useUnsavedChanges>;
}) {
  if (blocker.state !== "blocked") return null;

  return (
    <div className="dialog-backdrop">
      <section
        className="confirmation-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="unsaved-title"
        aria-describedby="unsaved-detail"
      >
        <span className="eyebrow">Unsaved changes</span>
        <h2 id="unsaved-title">Leave this editor?</h2>
        <p id="unsaved-detail">Your changes have not been saved and will be discarded.</p>
        <div className="dialog-actions">
          <button className="button secondary" type="button" onClick={() => blocker.reset()}>
            Keep editing
          </button>
          <button className="button danger" type="button" onClick={() => blocker.proceed()}>
            Discard changes
          </button>
        </div>
      </section>
    </div>
  );
}
