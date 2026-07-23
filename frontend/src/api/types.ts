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
  constraints?: Array<{
    constraint_type: string;
    value_json: Record<string, unknown>;
    source?: "user";
    confirmed: boolean;
  }>;
  work_calendar?: {
    weekday_hours: Record<string, number>;
    holidays: string[];
    parallel_limit: number;
  };
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

export type PlanState =
  | "idea"
  | "clarification_required"
  | "generating"
  | "draft"
  | "under_review"
  | "approved"
  | "active"
  | "archived"
  | "superseded";

export interface PlanVersionSummary {
  id: string;
  project_id: string;
  number: number;
  state: PlanState;
  based_on_id: string | null;
  reason: string;
  content_hash: string;
  quality_status: "passed" | "failed";
  row_version: number;
  created_at: string;
  updated_at: string;
}

export interface PlanAnalysisView {
  id: string;
  version_id: string;
  summary: string;
  project_type: string;
  intended_users: string[];
  objectives: Array<Record<string, unknown>>;
  success_criteria: Array<Record<string, unknown>>;
  modules: Array<Record<string, unknown>>;
  workstreams: string[];
  assumptions: Array<Record<string, unknown>>;
  constraints: Array<Record<string, unknown>>;
  complexity: string;
  mvp_boundary: string[];
  excluded_scope: string[];
}

export interface MilestoneView {
  id: string;
  version_id: string;
  stable_key: string;
  module_refs: string[];
  name: string;
  description: string;
  objective: string;
  deliverable: string;
  sequence: number;
  target_date: string | null;
  planned_effort_hours: string;
  acceptance_criteria: string[];
  planned_start: string | null;
  planned_finish: string | null;
  status: string;
  source: "ai" | "user";
  protected: boolean;
  locked: boolean;
  row_version: number;
}

export interface TaskView {
  id: string;
  version_id: string;
  milestone_id: string;
  parent_id: string | null;
  stable_key: string;
  title: string;
  description: string;
  deliverable: string;
  acceptance_criteria: string[];
  definition_of_done: string[];
  effort_min_hours: string;
  effort_likely_hours: string;
  effort_max_hours: string;
  complexity: "trivial" | "low" | "medium" | "high";
  workstreams: string[];
  skill_tags: string[];
  source: "ai" | "user";
  requirement_refs: string[];
  assumption_refs: string[];
  locked: boolean;
  protected: boolean;
  priority_score: string;
  priority_label: string;
  priority_breakdown: Record<string, unknown>;
  planned_start: string | null;
  planned_finish: string | null;
  status: string;
  row_version: number;
}

export interface DependencyView {
  id: string;
  version_id: string;
  predecessor_id: string;
  successor_id: string;
  dependency_type: "finish_to_start";
  reason: string;
  evidence_refs: string[];
  confidence_label: "low" | "medium" | "high";
  source: "ai" | "user";
  protected: boolean;
}

export interface PlanApprovalView {
  id: string;
  project_id: string;
  version_id: string;
  actor_id: string;
  decision: "approved" | "changes_requested" | "rejected";
  reason: string | null;
  content_hash: string;
  created_at: string;
}

export interface PlanGraphView extends PlanVersionSummary {
  quality_report: Record<string, unknown>;
  analysis: PlanAnalysisView | null;
  milestones: MilestoneView[];
  tasks: TaskView[];
  dependencies: DependencyView[];
  risks: Array<Record<string, unknown>>;
  approvals: PlanApprovalView[];
}

export interface PlanValidationView {
  passed: boolean;
  issues: Array<{
    severity: "must" | "should";
    code: string;
    path: string;
    message: string;
    references: string[];
  }>;
  warning_codes: string[];
  calculation_versions: Record<string, string>;
  content_hash: string;
  row_version: number;
}

export interface PlanDiffView {
  from_version_id: string;
  to_version_id: string;
  changes: Array<Record<string, unknown>>;
}

export interface PriorityFactorsPayload {
  mvp_necessity: number;
  deadline_urgency: number;
  user_value: number;
  risk_reduction: number;
  user_preference: number;
}

export interface TaskCreatePayload {
  milestone_id: string;
  parent_id?: string | null;
  title: string;
  description: string;
  deliverable: string;
  acceptance_criteria: string[];
  definition_of_done: string[];
  effort_min_hours: number;
  effort_likely_hours: number;
  effort_max_hours: number;
  complexity: "trivial" | "low" | "medium" | "high";
  workstreams: string[];
  skill_tags?: string[];
  requirement_refs?: string[];
  assumption_refs?: string[];
  priority_factors: PriorityFactorsPayload;
  locked?: boolean;
}

export interface MilestoneCreatePayload {
  module_refs: string[];
  name: string;
  description: string;
  objective: string;
  deliverable: string;
  sequence: number;
  target_date?: string | null;
  planned_effort_hours: number;
  acceptance_criteria: string[];
  locked?: boolean;
}

export interface DependencyCreatePayload {
  predecessor_id: string;
  successor_id: string;
  reason: string;
  evidence_refs: string[];
  confidence_label: "low" | "medium" | "high";
}
