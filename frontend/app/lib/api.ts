/**
 * API helper for communicating with the CareerOS FastAPI backend.
 * 
 * Why a thin wrapper instead of Axios?
 * - Native fetch is built into every browser and Next.js — zero extra dependencies.
 * - Our API calls are simple JSON requests — no need for interceptors or cancellation tokens.
 * - If we ever need those features, we can swap to Axios without changing the interface.
 */

export const API_BASE = process.env.NEXT_PUBLIC_CAREEROS_API_BASE || (typeof window !== "undefined" && window.location.hostname === "localhost"
  ? "http://localhost:8010"
  : "http://127.0.0.1:8010");

// ─── Generic fetch wrapper ──────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...options?.headers as Record<string, string>,
  };


  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...options,
    headers,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }

  return res.json();
}

// ─── Resume endpoints ───────────────────────────────────────────────

export interface ResumeVersion {
  id: string;
  source: string;
  original_filename: string | null;
  structured_json: any;
  design_json: any | null;
  builder_template_id: string | null;
  created_at: string;
}

export async function getResumes(): Promise<ResumeVersion[]> {
  return apiFetch<ResumeVersion[]>("/resumes/");
}

export async function getResumeById(resumeId: string): Promise<ResumeVersion> {
  return apiFetch<ResumeVersion>(`/resumes/${resumeId}`);
}

export async function uploadResume(file: File, source: string = "uploaded"): Promise<any> {
  const formData = new FormData();
  formData.append("file", file);

  const headers: Record<string, string> = {};

  const res = await fetch(`${API_BASE}/resumes/upload?source=${encodeURIComponent(source)}`, {
    method: "POST",
    body: formData,
    credentials: "include",
    headers,
    // Don't set Content-Type — browser sets it with the boundary for multipart
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Upload failed: ${res.status}`);
  }

  return res.json();
}

export async function deleteResume(resumeId: string): Promise<void> {
  return apiFetch(`/resumes/${resumeId}`, { method: "DELETE" });
}

/**
 * Download a PDF directly from a live builder payload.
 * No save required — just POST the current state and get a PDF blob back.
 */
export async function builderDownloadPdf(
  structuredJson: object,
  templateId: string,
  sectionOrder: string[],
  design: object,
  filename: string = "resume"
): Promise<void> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const res = await fetch(`${API_BASE}/resumes/builder-download-pdf`, {
    method: "POST",
    credentials: "include",
    headers,
    body: JSON.stringify({
      structured_json: structuredJson,
      template_id: templateId,
      section_order: sectionOrder,
      design,
      filename,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `PDF download failed: ${res.status}`);
  }
  // Trigger browser file download from the response blob
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filename}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}


export async function deleteAllResumes(): Promise<{ status: string; message: string }> {
  return apiFetch("/resumes/all", { method: "DELETE" });
}

export async function renameResume(resumeId: string, name: string): Promise<{ status: string; name: string }> {
  return apiFetch(`/resumes/${resumeId}/rename`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function duplicateResume(resumeId: string): Promise<{ status: string; resume_id: string; name: string }> {
  return apiFetch(`/resumes/${resumeId}/duplicate`, { method: "POST" });
}

// ─── Skills endpoints ───────────────────────────────────────────────

export interface Skill {
  id: string;
  name: string;
  source_resume_id: string | null;
  confidence: number | null;
  first_seen_at: string;
}

export async function getSkills(): Promise<Skill[]> {
  return apiFetch<Skill[]>("/skills/");
}

export async function addSkill(name: string): Promise<Skill> {
  return apiFetch<Skill>("/skills/", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function addSkillsBatch(skills: string[], sourceResumeId?: string): Promise<Skill[]> {
  return apiFetch<Skill[]>("/skills/batch", {
    method: "POST",
    body: JSON.stringify({ skills, source_resume_id: sourceResumeId }),
  });
}

export async function deleteSkill(skillId: string): Promise<void> {
  return apiFetch(`/skills/${skillId}`, { method: "DELETE" });
}

// ─── ATS Analysis endpoints ────────────────────────────────────────

export interface PremiumBreakdown {
  hard_skills_found: number;
  soft_skills_found: number;
  skills_used_in_context: number;
  has_certifications: boolean;
  cert_bonus_pts: number;
  has_volunteer_or_awards: boolean;
  estimated_word_count: number;
  years_experience: number;
  section_order: string[];
}

export interface ATSIssue {
  category: string;
  severity: "high" | "medium" | "low";
  issue: string;
  suggestion: string;
  points_deducted: number;
}

export interface BulletAnnotation {
  bullet: string;
  quality: "excellent" | "good" | "acceptable" | "needs_work";
  annotations: { type: "positive" | "warning" | "suggestion"; icon: string; text: string }[];
}

export interface BulletSectionAnnotation {
  item_index: number;
  title: string;
  company?: string;
  bullet_annotations: BulletAnnotation[];
}

export interface BulletAnnotationsResult {
  experience: BulletSectionAnnotation[];
  projects: BulletSectionAnnotation[];
  summary_stats: {
    total_bullets: number;
    excellent: number;
    good: number;
    acceptable: number;
    needs_work: number;
  };
}

export interface ATSResult {
  mode: string;                       // "baseline" | "targeted"
  resume_id?: string;
  // Bug 2: three distinct, honestly-named scores
  baseline_score?: number;            // resume strength, JD-independent; always present
  match_score?: number | null;        // resume-to-JD match; targeted only; null when JD unreadable
  overall_score?: number;             // headline blend; always present
  // JD extraction quality (Bug 4)
  jd_extraction_status?: "ok" | "low_confidence" | "failed";  // absent in baseline mode
  match_fallback_reason?: string;     // present when match_score is null
  // Keywords
  missing_keywords?: string[];
  matched_keywords?: string[];
  // Breakdown & analysis
  score_breakdown?: Record<string, number>;
  issues?: ATSIssue[];
  summary?: string;
  suggestions_created: SuggestionItem[];
  bullet_point_analysis?: any;
  // Legacy / optional
  keyword_details?: { keyword: string; status: "matched" | "missing"; found_in_sections: string[]; frequency: number }[];
  formatting_health?: Record<string, boolean>;
  bullet_annotations?: BulletAnnotationsResult;
}

export interface SuggestionItem {
  id: string;
  reason: string;
  original?: string;
  suggested?: string;
  category?: string;
  severity?: string;
  suggestion?: string;
  status: string;
}

export async function analyzeATS(
  resumeId: string,
  jobDescription?: string
): Promise<ATSResult> {
  return apiFetch<ATSResult>("/analyze", {
    method: "POST",
    body: JSON.stringify({
      resume_id: resumeId,
      job_description: jobDescription || null,
    }),
  });
}

export interface ChangeItem {
  id?: string;
  section: string;
  item_index: number;
  bullet_index: number | null;
  field: string;
  original: string;
  proposed: string;
  reason: string;
  type: string; // "rewrite" or "question"
  user_answer?: string | null;
  category?: string;
}

export interface ImproveProposeResult {
  status: string;
  proposed_changes: ChangeItem[];
  old_score: number | string;
}

export async function improvePropose(
  resumeId: string,
  mode: string = "auto_improve",
  customCategory?: string,
  jobDescription?: string
): Promise<ImproveProposeResult> {
  return apiFetch<ImproveProposeResult>("/improve/propose", {
    method: "POST",
    body: JSON.stringify({
      resume_id: resumeId,
      mode,
      custom_category: customCategory || null,
      job_description: jobDescription || null,
    }),
  });
}

export interface ImproveApplyResult {
  status: string;
  improved_resume_id: string;
  new_score?: number | string;
  improved_json: any;
  download_url: string;
}

export async function improveApply(
  resumeId: string,
  acceptedChanges: ChangeItem[]
): Promise<ImproveApplyResult> {
  return apiFetch<ImproveApplyResult>("/improve/apply", {
    method: "POST",
    body: JSON.stringify({
      resume_id: resumeId,
      accepted_changes: acceptedChanges,
    }),
  });
}

export interface ImproveBulletResult {
  suggested: string;
  reasoning: string;
}

export async function improveBullet(
  bulletText: string,
  jobDescription?: string
): Promise<ImproveBulletResult> {
  return apiFetch<ImproveBulletResult>("/improve-bullet", {
    method: "POST",
    body: JSON.stringify({
      bullet_text: bulletText,
      job_description: jobDescription || null,
    }),
  });
}


// ─── Suggestions endpoints ──────────────────────────────────────────

export interface Suggestion {
  id: string;
  type: string;
  reason: string;
  confidence_score: number | null;
  expected_impact: string | null;
  status: string;
  payload: any;
  created_at: string;
}

export async function getSuggestions(status?: string): Promise<Suggestion[]> {
  const query = status ? `?status=${status}` : "";
  return apiFetch<Suggestion[]>(`/suggestions/${query}`);
}

export async function updateSuggestion(
  suggestionId: string,
  status: "accepted" | "rejected" | "edited",
  editedPayload?: any
): Promise<Suggestion> {
  return apiFetch<Suggestion>(`/suggestions/${suggestionId}`, {
    method: "PATCH",
    body: JSON.stringify({ status, edited_payload: editedPayload || null }),
  });
}

// ─── Chat endpoints ─────────────────────────────────────────────────

export interface ChatSource {
  chunk_text: string;
  score: number;
  source_filename: string | null;
  resume_version_id: string | null;
}

export interface TailoredResumeDetail {
  resume_id: string;
  original_resume_id: string | null;
  changes_summary: string;
}

export interface PushEventDetail {
  id: string;
  repo_name: string;
  description: string | null;
  files: { path: string; content: string }[] | null;
}

export interface ChatSendResponse {
  answer: string;
  sources: ChatSource[];
  session_id: string;
  user_message_id: string;
  assistant_message_id: string;
  push_event?: PushEventDetail | null;
  tailor_event?: TailoredResumeDetail | null;
}

export interface ChatMessageItem {
  id: string;
  role: "user" | "assistant";
  content: string;
  session_id: string;
  created_at: string;
}

export async function sendChatMessage(
  message: string,
  sessionId?: string,
  file?: File,
  signal?: AbortSignal
): Promise<ChatSendResponse> {
  const formData = new FormData();
  formData.append("message", message);
  if (sessionId) {
    formData.append("session_id", sessionId);
  }
  if (file) {
    formData.append("file", file);
  }

  const res = await fetch(`${API_BASE}/chat/send`, {
    method: "POST",
    body: formData,
    credentials: "include",
    signal,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Chat send failed: ${res.status}`);
  }

  return res.json();
}

export async function getChatHistory(sessionId?: string): Promise<ChatMessageItem[]> {
  const query = sessionId ? `?session_id=${sessionId}` : "";
  return apiFetch<ChatMessageItem[]>(`/chat/history${query}`);
}

export async function createChatSession(): Promise<{ session_id: string }> {
  return apiFetch<{ session_id: string }>("/chat/sessions", {
    method: "POST",
  });
}

// ─── GitHub endpoints ───────────────────────────────────────────────

export interface GitHubStatus {
  connected: boolean;
  github_username: string | null;
  scope: string | null;
  connected_at: string | null;
}

export interface PushResult {
  status: string;
  repo_url: string | null;
  commit_sha: string | null;
  files_pushed: number;
  error: string | null;
}

export async function getGitHubStatus(): Promise<GitHubStatus> {
  return apiFetch<GitHubStatus>("/github/status");
}

export async function connectGitHub(): Promise<{ auth_url: string; state: string }> {
  return apiFetch<{ auth_url: string; state: string }>("/github/connect");
}

export async function githubCallback(code: string, state?: string): Promise<any> {
  const query = state ? `?code=${code}&state=${state}` : `?code=${code}`;
  return apiFetch(`/github/callback${query}`);
}

export async function disconnectGitHub(): Promise<void> {
  return apiFetch("/github/disconnect", { method: "DELETE" });
}

export async function pushToGitHub(
  repoName: string,
  files: { path: string; content: string }[],
  description?: string,
  isPrivate?: boolean,
  pushEventId?: string,
): Promise<PushResult> {
  return apiFetch<PushResult>("/github/push", {
    method: "POST",
    body: JSON.stringify({
      repo_name: repoName,
      description: description || "",
      private: isPrivate || false,
      files,
      push_event_id: pushEventId,
    }),
  });
}

export async function extractResumeText(file: File): Promise<{ status: string; filename: string; text: string }> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/resumes/extract-text`, {
    method: "POST",
    body: formData,
    credentials: "include",
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Text extraction failed: ${res.status}`);
  }

  return res.json();
}

export async function analyzeATSText(
  resumeText: string,
  jobDescription?: string
): Promise<ATSResult> {
  return apiFetch<ATSResult>("/analyze-text", {
    method: "POST",
    body: JSON.stringify({
      resume_text: resumeText,
      job_description: jobDescription || null,
    }),
  });
}

// ─── Tailor endpoints (new clean API) ────────────────────────────────

export interface TailorSession {
  id: string;
  label: string;
  version_number: number;
  score: number | null;
  original_resume_id: string | null;
  created_at: string | null;
  download_pdf_url: string;
  download_docx_url: string;
}

export async function getTailorSessions(): Promise<TailorSession[]> {
  const runs = await apiFetch<{ id: string; label: string; status: string; created_at: string; pdf_url: string | null }[]>("/tailor/runs");
  return runs.filter(r => r.status === "ready").map((r, i) => ({ id: r.id, label: r.label, version_number: i + 1, score: null, original_resume_id: null, created_at: r.created_at, download_pdf_url: r.pdf_url ? `${API_BASE}${r.pdf_url}` : "", download_docx_url: "" }));
}

export async function getTemplates(): Promise<{ id: string; name: string; description: string; font_family: string; default_font_id: string }[]> {
  return apiFetch<{ id: string; name: string; description: string; font_family: string; default_font_id: string }[]>("/resumes/templates");
}

// ─── Resume Builder endpoints ───────────────────────────────────────

export async function previewResumeHtml(
  structuredJson: any,
  templateId: string = "classic",
  fontId?: string,
  sectionOrder?: string[],
  design?: any
): Promise<{ html: string }> {
  return apiFetch<{ html: string }>("/resumes/preview-html", {
    method: "POST",
    body: JSON.stringify({
      structured_json: structuredJson,
      template_id: templateId,
      font_id: fontId,
      section_order: sectionOrder,
      design: design,
    }),
  });
}

export async function builderSave(
  structuredJson: any,
  designJson?: any,
  templateId?: string,
  fontId?: string,
  sectionOrder?: string[],
  resumeId?: string,
  originalFilename?: string
): Promise<{ resume_id: string; message: string }> {
  return apiFetch<{ resume_id: string; message: string }>("/resumes/builder-save", {
    method: "POST",
    body: JSON.stringify({
      resume_id: resumeId || null,
      structured_json: structuredJson,
      design_json: designJson || null,
      template_id: templateId || "classic",
      font_id: fontId || null,
      section_order: sectionOrder || null,
      original_filename: originalFilename || "My Resume",
    }),
  });
}

export async function uploadAvatar(file: File): Promise<{ url: string; filename: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/resumes/upload-avatar`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }
  return res.json();
}

export function getResumePdfUrl(resumeId: string, templateId?: string, fontId?: string): string {
  const params = new URLSearchParams();
  if (templateId) params.set("template_id", templateId);
  if (fontId) params.set("font_id", fontId);
  return `${API_BASE}/resumes/${resumeId}/pdf?${params.toString()}`;
}

