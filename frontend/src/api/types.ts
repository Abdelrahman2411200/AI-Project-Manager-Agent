export interface UserView {
  id: string;
  email: string;
  status: string;
}

export interface SessionView {
  user: UserView;
  expires_at: string;
  csrf_token: string | null;
}

export interface RequirementView {
  id: string;
  kind: "stated" | "suggestion" | "confirmed" | "excluded";
  text: string;
  source: "user" | "agent" | "system";
  status: "open" | "confirmed" | "rejected";
  created_at: string;
}

export interface ConstraintView {
  id: string;
  constraint_type: string;
  value_json: Record<string, unknown>;
  source: "user" | "agent" | "system";
  confirmed: boolean;
  created_at: string;
}

export interface WorkCalendarView {
  id: string;
  weekday_hours: Record<string, number>;
  holidays: string[];
  effective_from: string | null;
  effective_to: string | null;
  parallel_limit: number;
}

export interface ProjectView {
  id: string;
  name: string;
  goal: string;
  desired_outcome: string | null;
  start_date: string | null;
  deadline: string | null;
  timezone: string;
  capacity_hours_per_week: string;
  team_size: number;
  status: "active" | "archived";
  notes: string | null;
  row_version: number;
  created_at: string;
  updated_at: string;
  requirements: RequirementView[];
  constraints: ConstraintView[];
  calendars: WorkCalendarView[];
}

export interface ProjectList {
  items: ProjectView[];
  next_cursor: string | null;
}

export interface ProjectCreatePayload {
  name: string;
  goal: string;
  desired_outcome?: string;
  start_date?: string;
  deadline?: string;
  timezone: string;
  capacity_hours_per_week: number;
  team_size: number;
  notes?: string;
  requirements: Array<{
    kind: "stated" | "excluded";
    text: string;
    status: "open" | "confirmed";
  }>;
}

export type AgentRunStatus =
  | "queued"
  | "running"
  | "waiting_for_user"
  | "partial"
  | "failed"
  | "completed"
  | "cancelled";

export interface AgentRunView {
  id: string;
  project_id: string;
  workflow: "planning";
  status: AgentRunStatus;
  current_step: string;
  token_budget: number;
  tokens_used: number;
  cancel_requested: boolean;
  proposed_plan_version_id: string | null;
  outcome: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface AgentRunStepView {
  id: string;
  name: string;
  mode: "deterministic" | "llm" | "human" | "transactional";
  purpose: string;
  attempt: number;
  status: string;
  input_refs: Array<Record<string, unknown>>;
  output_refs: Array<Record<string, unknown>>;
  validation: Array<Record<string, unknown>>;
  usage: Record<string, unknown>;
  failure_code: string | null;
  retryable: boolean;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
}

export interface ClarificationView {
  id: string;
  run_id: string;
  stable_key: string;
  question: string;
  reason: string;
  affects: string[];
  required: boolean;
  answer_type: "text" | "number" | "boolean" | "date" | "single_choice" | "multi_choice";
  options: string[];
  default_assumption: string | null;
  source_fact_refs: string[];
  answer_json: unknown;
  status: "open" | "answered" | "assumed" | "dismissed";
  created_at: string;
  updated_at: string;
}

export interface ClarificationResumeView {
  run: AgentRunView;
  questions: ClarificationView[];
  resumed: boolean;
}
