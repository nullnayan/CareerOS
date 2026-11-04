import { API_BASE } from "./api";

export type AIRepairReport = { original_id: string; status: string; message: string; attempts: { number: number; status: string; message: string }[]; diff: string; retry_after?: number; master?: Master | null };

export type Master = {
  id: string; filename: string; source_hash: string; categories: string[]; status: string;
  baseline_pages: number | null; diagnostics: string | null; pdf_url: string | null;
  reference_pdf_url: string | null; created_at: string; recovery_pdf_url?: string | null; project_url?: string | null;
  compatibility?: {
    engine: string; detected_engine: string; mapping_supported: boolean; mapping_error?: string | null;
    project_files: string[]; main_file: string; issues: { message: string; line?: number; suggestion?: string }[];
  } | null;
  ai_repair?: AIRepairReport | null;
  comparison?: { reference_pages: number; baseline_pages: number; reference_text_coverage: number | null; missing_reference_excerpt?: string | null; note?: string } | null;
};
export type Candidate = { canonical: string; name: string; category: string; confirmed: boolean; excerpt: string; importance: string };
export type TailoringRun = { id: string; master_id: string; label: string; job_description?: string; candidates: Candidate[]; status: string; diagnostics: string; changes: { category: string; before: string; after: string; added: string[] }[] | null; pdf_url: string | null; source_url: string | null; project_url?: string | null; created_at: string };

export async function personal<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const form = body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, { method, headers: body && !form ? { "Content-Type": "application/json" } : undefined, body: body ? (form ? body : JSON.stringify(body)) as BodyInit : undefined });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed. Check the supplied fields.");
  return data;
}

export function artifactUrl(path: string) { return `${API_BASE}${path}`; }
