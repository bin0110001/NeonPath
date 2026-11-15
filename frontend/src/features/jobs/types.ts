export interface JobRequirement {
  type: string;
  normalized_text: string;
  source_text?: string;
  required_level?: string;
  category?: string;
  confidence?: number;
}

export interface JobSource {
  adapter: string;
  external_id?: string;
  source_url?: string;
}

export interface Job {
  id: string;
  title: string;
  company: string;
  company_domain?: string;
  description_text?: string;
  description_html?: string;
  location_text?: string;
  remote_type?: string;
  employment_type?: string;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: string;
  salary_period?: string;
  canonical_url?: string;
  discovered_at: string;
  requirements?: JobRequirement[];
  sources?: JobSource[];
}

export interface JobEvaluation {
  overall_score: number;
  confidence?: number;
  explanation?: string;
  strengths?: string[];
  gaps?: string[];
  blockers?: string[];
  dimension_scores_json?: Record<string, number>;
}
