/**
 * frontend/app/lib/resumeSchema.ts
 * =================================
 * Canonical TypeScript types mirroring backend/schemas/resume.py
 * schema_version = 1
 *
 * This is the single source of truth for the resume data shape on the frontend.
 * All builder state, API payloads, and preview requests must use these types.
 */

export const SCHEMA_VERSION = 1;

// ── Sub-types ──────────────────────────────────────────────────────────────

export interface CustomField {
  id: string;
  label: string;
  value: string;
}

export interface Contact {
  name: string;
  headline: string;
  email: string;
  phone: string;
  location: string;
  website: string;
  custom_fields: CustomField[];
}

export interface ProfileLink {
  id: string;
  network: string;    // e.g. "GitHub", "LinkedIn"
  username: string;
  url: string;
  hidden: boolean;
}

export interface Photo {
  url: string;        // server path or data URI
  hidden: boolean;
  size: number;       // px width
  border_radius: number; // %
  border_color: string;
  border_width: number;  // px
  shadow_width: number;
  aspect_ratio: number;
  rotation: number;
}

export interface ExperienceItem {
  id: string;
  hidden: boolean;
  company: string;
  position: string;   // canonical (alias: title in old data)
  location: string;
  start_date: string;
  end_date: string;
  url: string;
  bullet_points: string[];
}

export interface EducationItem {
  id: string;
  hidden: boolean;
  institution: string;
  degree: string;
  field: string;
  grade: string;      // canonical (alias: cgpa_or_percentage in old data)
  location: string;
  graduation_date: string;
  description: string;
}

export interface ProjectItem {
  id: string;
  hidden: boolean;
  name: string;
  period: string;     // canonical (alias: date in old data)
  url: string;        // canonical (alias: link in old data)
  technologies: string[];
  bullets: string[];
}

export interface SkillItem {
  id: string;
  hidden: boolean;
  name: string;
  level: number;      // 0–5
  keywords: string[];
}

export interface LanguageItem {
  id: string;
  hidden: boolean;
  language: string;
  fluency: string;    // e.g. "Native", "Fluent"
  level: number;
}

export interface AwardItem {
  id: string;
  hidden: boolean;
  title: string;
  awarder: string;
  date: string;
  description: string;
}

export interface CertItem {
  id: string;
  hidden: boolean;
  title: string;
  issuer: string;
  date: string;
  url: string;
  description: string;
}

export interface PubItem {
  id: string;
  hidden: boolean;
  title: string;
  publisher: string;
  date: string;
  url: string;
  summary: string;
}

export interface VolunteerItem {
  id: string;
  hidden: boolean;
  organization: string;
  position: string;
  location: string;
  period: string;
  description: string;
}

export interface InterestItem {
  id: string;
  hidden: boolean;
  name: string;
  keywords: string[];
}

export interface ReferenceItem {
  id: string;
  hidden: boolean;
  name: string;
  position: string;
  phone: string;
  url: string;
  description: string;
}

export interface CustomSectionItem {
  id: string;
  hidden: boolean;
  title: string;
  subtitle: string;
  date: string;
  bullets: string[];
}

export interface CustomSection {
  id: string;
  hidden: boolean;
  name: string;
  items: CustomSectionItem[];
}

// ── Root type ──────────────────────────────────────────────────────────────

export const DEFAULT_SECTION_ORDER = [
  "summary", "experience", "education", "projects",
  "skills", "languages", "certifications", "awards",
  "publications", "volunteer", "interests", "references", "custom_sections",
] as const;

export type SectionKey = typeof DEFAULT_SECTION_ORDER[number];

export interface ResumeJSON {
  schema_version: 1;

  contact: Contact;
  photo: Photo;
  summary: string;
  profiles: ProfileLink[];

  experience: ExperienceItem[];
  education: EducationItem[];
  projects: ProjectItem[];
  skills: SkillItem[];
  languages: LanguageItem[];
  awards: AwardItem[];
  certifications: CertItem[];
  publications: PubItem[];
  volunteer: VolunteerItem[];
  interests: InterestItem[];
  references: ReferenceItem[];
  custom_sections: CustomSection[];

  section_order: string[];
  section_visibility: Record<string, boolean>;
}

// ── Default factory ────────────────────────────────────────────────────────

export function makeEmptyResume(): ResumeJSON {
  return {
    schema_version: 1,
    contact: { name: "", headline: "", email: "", phone: "", location: "", website: "", custom_fields: [] },
    photo: { url: "", hidden: false, size: 80, border_radius: 50, border_color: "#e5e7eb", border_width: 0, shadow_width: 0, aspect_ratio: 1, rotation: 0 },
    summary: "",
    profiles: [],
    experience: [],
    education: [],
    projects: [],
    skills: [],
    languages: [],
    awards: [],
    certifications: [],
    publications: [],
    volunteer: [],
    interests: [],
    references: [],
    custom_sections: [],
    section_order: [...DEFAULT_SECTION_ORDER],
    section_visibility: {},
  };
}
