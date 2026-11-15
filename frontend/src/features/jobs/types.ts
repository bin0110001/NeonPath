// Mirrors backend/src/careerflow/api/schemas/jobs.py

export type RemoteType = "REMOTE" | "HYBRID" | "ONSITE";
export type EmploymentType = "FULL_TIME" | "PART_TIME" | "CONTRACT" | "TEMPORARY" | "INTERNSHIP";
export type SalaryPeriod = "YEAR" | "MONTH" | "WEEK" | "DAY" | "HOUR";

export type WorkflowStatus =
  | "READY_FOR_REVIEW"
  | "SHORTLISTED"
  | "SAVED"
  | "ARCHIVED"
  | "PREPARING"
  | "READY_TO_APPLY"
  | "APPLIED"
  | "SCREENING"
  | "INTERVIEWING"
  | "FINAL"
  | "OFFER"
  | "REJECTED"
  | "WITHDRAWN";

export interface Job {
  id: string;
  title: string;
  company: string;
  description_text: string;
  canonical_url: string | null;
  company_domain: string | null;
  description_html: string | null;
  location_text: string | null;
  remote_type: RemoteType | null;
  employment_type: EmploymentType | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: SalaryPeriod | null;
  posted_at: string | null;
  expires_at: string | null;
  discovered_at: string;
  source_updated_at: string | null;
  source_status: string | null;
  fingerprint: string | null;
  status: string;
  raw_metadata_json: Record<string, unknown>;
}

export interface JobSourceRecord {
  id: string;
  job_id: string;
  adapter: string;
  external_id: string | null;
  source_url: string | null;
  raw_payload: Record<string, unknown>;
  discovered_at: string;
  last_seen_at: string;
}

export interface JobRequirement {
  id: string;
  job_id: string;
  type: string;
  normalized_text: string;
  source_text: string;
  required_level: string | null;
  category: string | null;
  confidence: number | null;
}

export interface JobEvaluation {
  id: string;
  job_id: string;
  profile_id: string;
  evaluator_version: string;
  model_provider: string | null;
  model_name: string | null;
  overall_score: number;
  confidence: number | null;
  dimension_scores_json: Record<string, number>;
  strengths: string[];
  transferable_matches: string[];
  gaps: string[];
  blockers: string[];
  unknowns: string[];
  explanation: string | null;
  created_at: string;
}

export interface WorkflowState {
  job_id: string;
  profile_id: string;
  status: WorkflowStatus;
}

export interface StatusHistoryEntry {
  id: string;
  job_id: string;
  profile_id: string;
  old_status: string | null;
  new_status: string;
  actor: string | null;
  reason: string | null;
  timestamp: string;
}

export interface ProfileSummary {
  id: string;
  display_name: string;
}
