// ─── Job Role ───────────────────────────────────────────────
export interface JobRole {
  id: string;
  title: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  resume_count: number;
}

export interface JobRoleCreate {
  title: string;
  description?: string;
}

export interface JobRoleUpdate {
  title?: string;
  description?: string | null;
}

// ─── Job Description ────────────────────────────────────────
export interface JDRequirements {
  mandatory_skills: string[];
  preferred_skills: string[];
  min_experience_years: number;
  certifications: string[];
}

export interface JobDescription {
  id: string;
  job_role_id: string;
  raw_text: string;
  requirements: JDRequirements;
  is_active: boolean;
  created_at: string;
  status: "ready" | "pending";
}

// ─── Candidate Ranking ──────────────────────────────────────
export interface CandidateInMatch {
  id: string;
  resume_upload_id: string;
  full_name: string;
  email: string | null;
  total_exp_years: number;
  skills: string[];
  is_low_confidence: boolean;
  profile_json?: Record<string, any>;
}

export interface CandidateRankingResult {
  candidate: CandidateInMatch;
  semantic_score: number;
  rule_score: number;
  final_score: number;
  score_breakdown_json: Record<string, any>;
  justification_text: string | null;
  justification_model: string | null;
  ranked_at: string | null;
}

export interface JobDescriptionRankingResponse {
  jd_id: string;
  total_candidates: number;
  returned_candidates: number;
  candidates: CandidateRankingResult[];
}

// ─── Scoring Config ─────────────────────────────────────────
export interface ScoringConfig {
  id: string;
  job_role_id: string;
  preset_name: string;
  is_customised: boolean;
  updated_at: string;
  updated_by: string | null;
  skill_match_weight: number;
  exp_years_weight: number;
  projects_weight: number;
  prof_exp_weight: number;
  certs_weight: number;
}

export interface ScoringConfigUpdate {
  skill_match_weight: number;
  exp_years_weight: number;
  projects_weight: number;
  prof_exp_weight: number;
  certs_weight: number;
}

// ─── Resume Upload ──────────────────────────────────────────
export type ResumeUploadStatus =
  | "uploaded"
  | "queued"
  | "parsing"
  | "parsed"
  | "failed";

export interface UploadResponse {
  id: string;
  original_name: string;
  status: ResumeUploadStatus | null;
  error_message: string | null;
}

export interface BatchUploadResponse {
  uploaded: UploadResponse[];
  failed: UploadResponse[];
}

export interface UploadStatusResponse {
  id: string;
  original_name: string;
  status: ResumeUploadStatus;
  error_message: string | null;
  file_key: string | null;
}

export interface ResumeUploadListItem {
  id: string;
  original_name: string;
  status: ResumeUploadStatus;
  error_message: string | null;
  uploaded_at: string;
}
