import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { updatePlanVersion } from "../../../api/plans";
import type { PlanGraphView } from "../../../api/types";
import { errorMessage, isConflict } from "../../../api/errorUtils";
import { FeedbackBanner } from "../../../components/Feedback";
import { UnsavedChangesDialog } from "../../../components/UnsavedChangesDialog";
import { useUnsavedChanges } from "../../../hooks/useUnsavedChanges";

const schema = z.object({
  summary: z.string().trim().min(20, "Add a summary of at least 20 characters.").max(4000),
  mvp_boundary: z.string(),
  excluded_scope: z.string(),
});

type Values = z.infer<typeof schema>;

function lines(value: string): string[] {
  return value.split("\n").map((line) => line.trim()).filter(Boolean);
}

interface AnalysisEditorProps {
  plan: PlanGraphView;
  onSaved: () => Promise<void>;
  onClose: () => void;
}

export function AnalysisEditor({ plan, onSaved, onClose }: AnalysisEditorProps) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      summary: plan.analysis?.summary ?? "",
      mvp_boundary: plan.analysis?.mvp_boundary.join("\n") ?? "",
      excluded_scope: plan.analysis?.excluded_scope.join("\n") ?? "",
    },
  });
  const blocker = useUnsavedChanges(form.formState.isDirty);
  const save = useMutation({
    mutationFn: (values: Values) =>
      updatePlanVersion(plan.id, plan.row_version, {
        analysis_summary: values.summary,
        mvp_boundary: lines(values.mvp_boundary),
        excluded_scope: lines(values.excluded_scope),
      }),
    onSuccess: async () => {
      form.reset(form.getValues());
      await onSaved();
      onClose();
    },
  });
  const submit = form.handleSubmit((values) => save.mutate(values));

  return (
    <>
      <section className="editor-panel" aria-labelledby="analysis-editor-title">
        <div className="editor-header">
          <div><span className="eyebrow">Owner edit</span><h2 id="analysis-editor-title">Edit plan analysis</h2></div>
          <button className="icon-button" type="button" aria-label="Close analysis editor" onClick={onClose}>×</button>
        </div>
        {save.isError ? (
          <FeedbackBanner tone={isConflict(save.error) ? "warning" : "danger"} title={isConflict(save.error) ? "The draft changed elsewhere" : "Analysis was not saved"}>
            {errorMessage(save.error, "Review the analysis and try again.")}
          </FeedbackBanner>
        ) : null}
        <form className="editor-form" noValidate onSubmit={(event) => void submit(event)}>
          <label>
            <span>Analysis summary</span>
            <textarea rows={7} {...form.register("summary")} />
            {form.formState.errors.summary ? <small className="field-error">{form.formState.errors.summary.message}</small> : null}
          </label>
          <div className="editor-grid">
            <label>
              <span>MVP boundary <small>One outcome per line</small></span>
              <textarea rows={6} {...form.register("mvp_boundary")} />
            </label>
            <label>
              <span>Excluded scope <small>One item per line</small></span>
              <textarea rows={6} {...form.register("excluded_scope")} />
            </label>
          </div>
          <div className="editor-actions">
            <button className="button secondary" type="button" onClick={onClose}>Cancel</button>
            <button className="button primary" type="submit" disabled={save.isPending || !form.formState.isDirty}>
              {save.isPending ? "Saving…" : "Save analysis"}
            </button>
          </div>
        </form>
      </section>
      <UnsavedChangesDialog blocker={blocker} />
    </>
  );
}
