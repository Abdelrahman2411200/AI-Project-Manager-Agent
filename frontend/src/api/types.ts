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
