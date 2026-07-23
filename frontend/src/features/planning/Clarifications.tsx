import { useEffect, useMemo } from "react";
import { useForm, useWatch } from "react-hook-form";

import type { ClarificationView } from "../../api/types";
import { FeedbackBanner } from "../../components/Feedback";

type AnswerValue = string | number | boolean | string[];
interface ClarificationFormValues {
  answers: Record<string, AnswerValue>;
}

interface ClarificationsProps {
  projectId: string;
  runId: string;
  questions: ClarificationView[];
  pending: boolean;
  error?: string;
  onSubmit: (answers: Array<{ question_id: string; answer: unknown }>) => void;
}

function storageKey(projectId: string, runId: string): string {
  return `apm:clarifications:${projectId}:${runId}`;
}

function storedAnswers(projectId: string, runId: string): Record<string, AnswerValue> {
  try {
    const value = sessionStorage.getItem(storageKey(projectId, runId));
    return value ? (JSON.parse(value) as Record<string, AnswerValue>) : {};
  } catch {
    return {};
  }
}

function assumptionValue(question: ClarificationView): AnswerValue | undefined {
  if (!question.default_assumption) return undefined;
  if (question.answer_type === "number") {
    const numberValue = Number(question.default_assumption);
    return Number.isFinite(numberValue) ? numberValue : undefined;
  }
  if (question.answer_type === "boolean") {
    if (question.default_assumption.toLowerCase() === "true") return true;
    if (question.default_assumption.toLowerCase() === "false") return false;
    return undefined;
  }
  if (question.answer_type === "single_choice") {
    return question.options.includes(question.default_assumption)
      ? question.default_assumption
      : undefined;
  }
  if (question.answer_type === "multi_choice") return undefined;
  return question.default_assumption;
}

function hasAnswer(value: AnswerValue | undefined): boolean {
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "string") return value.trim().length > 0;
  return value !== undefined;
}

export function Clarifications({
  projectId,
  runId,
  questions,
  pending,
  error,
  onSubmit,
}: ClarificationsProps) {
  const defaults = useMemo(() => {
    const saved = storedAnswers(projectId, runId);
    return Object.fromEntries(
      questions.map((question) => [
        question.id,
        saved[question.id] ??
          (question.status === "answered" ? (question.answer_json as AnswerValue) : ""),
      ]),
    );
  }, [projectId, questions, runId]);
  const form = useForm<ClarificationFormValues>({
    defaultValues: { answers: defaults },
  });
  const answers = useWatch({ control: form.control, name: "answers" });

  useEffect(() => {
    try {
      sessionStorage.setItem(storageKey(projectId, runId), JSON.stringify(answers ?? {}));
    } catch {
      // Storage may be disabled; the in-memory form remains fully usable.
    }
  }, [answers, projectId, runId]);

  const submit = form.handleSubmit((values) => {
    const submitted = questions.flatMap((question) => {
      const answer = values.answers[question.id];
      if (!hasAnswer(answer)) return [];
      return [{ question_id: question.id, answer }];
    });
    onSubmit(submitted);
  });

  return (
    <form
      className="clarification-form"
      noValidate
      onSubmit={(event) => void submit(event)}
    >
      {error ? <FeedbackBanner tone="danger" title="Answers could not be submitted">{error}</FeedbackBanner> : null}
      <div className="clarification-intro">
        <div>
          <span className="eyebrow">Decision checkpoint</span>
          <h2>Resolve planning questions</h2>
          <p>Your answers become stored project facts. Suggested assumptions stay explicitly labeled.</p>
        </div>
        <span className="autosave-state" role="status">Draft answers saved in this browser</span>
      </div>

      <ol className="clarification-list">
        {questions.map((question, index) => {
          const path = `answers.${question.id}` as const;
          const fieldError = form.formState.errors.answers?.[question.id];
          const suggestion = assumptionValue(question);
          return (
            <li className="clarification-card" key={question.id}>
              <div className="question-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</div>
              <fieldset>
                <legend>
                  {question.question}
                  {question.required ? <span className="required-mark">Required</span> : <span className="optional-mark">Optional</span>}
                </legend>
                <p className="question-reason">{question.reason}</p>
                {question.affects.length ? (
                  <p className="question-affects"><strong>Affects:</strong> {question.affects.join(", ")}</p>
                ) : null}

                {question.answer_type === "text" ? (
                  <textarea
                    rows={3}
                    aria-describedby={`${question.id}-help`}
                    {...form.register(path, {
                      required: question.required ? "Answer this required question." : false,
                    })}
                  />
                ) : null}
                {question.answer_type === "number" ? (
                  <input
                    type="number"
                    step="any"
                    {...form.register(path, {
                      required: question.required ? "Enter a number." : false,
                      setValueAs: (value) => value === "" ? "" : Number(value),
                    })}
                  />
                ) : null}
                {question.answer_type === "date" ? (
                  <input
                    type="date"
                    {...form.register(path, {
                      required: question.required ? "Choose a date." : false,
                    })}
                  />
                ) : null}
                {question.answer_type === "boolean" ? (
                  <select
                    {...form.register(path, {
                      required: question.required ? "Choose yes or no." : false,
                      setValueAs: (value) =>
                        value === "true" ? true : value === "false" ? false : "",
                    })}
                  >
                    <option value="">Choose an answer</option>
                    <option value="true">Yes</option>
                    <option value="false">No</option>
                  </select>
                ) : null}
                {question.answer_type === "single_choice" ? (
                  <div className="choice-grid">
                    {question.options.map((option) => (
                      <label className="choice-option" key={option}>
                        <input
                          type="radio"
                          value={option}
                          {...form.register(path, {
                            required: question.required ? "Choose one option." : false,
                          })}
                        />
                        <span>{option}</span>
                      </label>
                    ))}
                  </div>
                ) : null}
                {question.answer_type === "multi_choice" ? (
                  <div className="choice-grid">
                    {question.options.map((option) => (
                      <label className="choice-option" key={option}>
                        <input
                          type="checkbox"
                          value={option}
                          {...form.register(path, {
                            validate: (value) =>
                              !question.required ||
                              (Array.isArray(value) && value.length > 0) ||
                              "Choose at least one option.",
                          })}
                        />
                        <span>{option}</span>
                      </label>
                    ))}
                  </div>
                ) : null}

                <small id={`${question.id}-help`} className="question-help">
                  Reference {question.stable_key}
                </small>
                {fieldError?.message ? <small className="field-error" role="alert">{fieldError.message}</small> : null}
                {suggestion !== undefined ? (
                  <div className="assumption-option">
                    <div>
                      <strong>Suggested assumption</strong>
                      <span>{question.default_assumption}</span>
                    </div>
                    <button
                      className="button compact secondary"
                      type="button"
                      onClick={() => form.setValue(path, suggestion, { shouldDirty: true, shouldValidate: true })}
                    >
                      Use assumption
                    </button>
                  </div>
                ) : null}
              </fieldset>
            </li>
          );
        })}
      </ol>

      <div className="sticky-form-actions">
        <div>
          <strong>{questions.filter((question) => question.required).length} required decisions</strong>
          <span>Planning resumes when every required answer is valid.</span>
        </div>
        <button className="button primary" type="submit" disabled={pending}>
          {pending ? "Saving answers…" : "Save answers and resume"}
        </button>
      </div>
    </form>
  );
}
