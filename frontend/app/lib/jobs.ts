export type SearchPreferences = {
  target_roles: string[]; locations: string[]; work_modes: string[]; employment_types: string[];
  graduation_year: number | null; education_status: string; institution: string;
  earliest_joining_date: string | null; max_required_experience: number;
  minimum_salary_annual_inr: number | null; excluded_companies: string[];
  country_code: string; max_posting_age_days: number | null;
  degree?: string; course?: string;
};
export type Source = { health?: string; retry_at?: string; last_scan?: { scope: string; pages: number; complete_snapshot: boolean; truncation_reason?: string }; id: string; provider: string; board: string; company: string; enabled: boolean; last_error: string | null; last_count: number; last_checked_at: string | null; last_success_at: string | null };
export type Assessment = { eligibility: string; minimum_experience: number | null; reasons: string[]; blocked_reasons: string[]; unknowns: string[]; matched_skills: string[]; missing_skills: string[]; resume_evidence_available: boolean; employment_type: string; work_mode: string; };
export type Job = { id: string; title: string; company: string; location: string; apply_url: string; description_complete: boolean; description?: string; status: string; state: string; assessment: Assessment; facts: Record<string, any>; first_seen_at: string; last_seen_at: string; published_at: string | null; source_ids: string[]; resume_status: string | null; tailoring_run_id: string | null };
export type Feed = { diagnostics?: { eligible_matches: number; relevance_matches: number; salary_unverified_matches: number; salary_excluded: number; include_unverified_salary: boolean }; page: number; page_size: number; has_next: boolean; items: Job[]; total: number; stored: number; preferences_confirmed: boolean; master_active: boolean };
export type RegisterEntry = { observed_probe?: string | null; probe_date?: string | null; id: string; name: string; access: string; implementation: string; cost: string; conditions: string; checked_at: string | null; polling_floor_seconds: number | null; documentation_url: string | null };
export type Catalog = { engine?: "oss" | "legacy"; source_register: RegisterEntry[]; employer_candidates: string[]; employer_reviews?: { company: string; official_url: string | null; mapping_status: string; required_input: string }[]; company_boards: { provider: string; board: string; company: string; url: string }[]; adzuna_configured: boolean; external_only: { name: string; url: string }[] };
