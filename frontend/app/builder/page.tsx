"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from "react-resizable-panels";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
import { motion, AnimatePresence, Reorder } from "framer-motion";
import {
  User, Image as ImageIcon, AlignLeft, Link2, Briefcase, GraduationCap,
  FolderOpen, Zap, Globe, Trophy, Award, BookOpen, Heart, Users, Plus,
  ChevronDown, ChevronUp, Eye, EyeOff, Trash2, GripVertical, Copy,
  Palette, Type, Layout, FileText, Download, Save, ArrowLeft,
  ZoomIn, ZoomOut, Maximize2, RotateCcw, RotateCw, CheckCircle,
  Loader2, X, Edit3, Star, PanelLeftClose, PanelRightClose,
  PanelLeftOpen, PanelRightOpen, Layers, Settings, Sparkles, BarChart2,
  ThumbsUp, ThumbsDown, RefreshCw, AlertCircle, TrendingUp, ChevronRight
} from "lucide-react";
import {
  previewResumeHtml, builderSave, uploadAvatar, getResumes, getResumeById,
  getResumePdfUrl, builderDownloadPdf, analyzeATS, improvePropose, improveBullet,
  API_BASE, type ResumeVersion, type ATSResult, type ChangeItem
} from "../lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ContactData {
  name: string;
  headline: string;
  email: string;
  phone: string;
  location: string;
  website: string;
  custom_fields: { id: string; label: string; value: string }[];
}

interface ProfileItem { id: string; network: string; username: string; url: string; hidden: boolean; }
interface ExperienceItem { id: string; company: string; position: string; location: string; start_date: string; end_date: string; url: string; bullet_points: string[]; hidden: boolean; }
interface EducationItem { id: string; institution: string; degree: string; field: string; grade: string; location: string; graduation_date: string; description: string; hidden: boolean; }
interface ProjectItem { id: string; name: string; period: string; url: string; technologies: string[]; bullets: string[]; hidden: boolean; }
interface SkillItem { id: string; name: string; level: number; keywords: string[]; hidden: boolean; }
interface LanguageItem { id: string; language: string; fluency: string; level: number; hidden: boolean; }
interface AwardItem { id: string; title: string; awarder: string; date: string; description: string; hidden: boolean; }
interface CertItem { id: string; title: string; issuer: string; date: string; url: string; description: string; hidden: boolean; }
interface PubItem { id: string; title: string; publisher: string; date: string; url: string; summary: string; hidden: boolean; }
interface VolunteerItem { id: string; organization: string; position: string; location: string; period: string; description: string; hidden: boolean; }
interface InterestItem { id: string; name: string; keywords: string[]; hidden: boolean; }
interface ReferenceItem { id: string; name: string; position: string; phone: string; url: string; description: string; hidden: boolean; }
interface CustomSectionItem { id: string; title: string; subtitle: string; date: string; bullets: string[]; hidden: boolean; }
interface CustomSection { id: string; name: string; items: CustomSectionItem[]; hidden: boolean; }

interface ResumeData {
  contact: ContactData;
  photo: { url: string; hidden: boolean; size: number; border_radius: number; border_color: string; border_width: number; shadow_width: number; aspect_ratio: number; rotation: number; };
  summary: string;
  profiles: ProfileItem[];
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
}

interface DesignData {
  primary_color: string;
  text_color: string;
  background_color: string;
  font_family: string;
  font_size: number;
  line_height: number;
  sidebar_width: number;
  page_format: string;
  margin_x: number;
  margin_y: number;
}

type SectionKey = "photo" | "basics" | "summary" | "profiles" | "experience" | "education" | "projects" | "skills" | "languages" | "awards" | "certifications" | "publications" | "volunteer" | "interests" | "references" | "custom";
type SaveStatus = "idle" | "saving" | "saved" | "error";

// Canonical order of sections that appear in the resume body
const DEFAULT_SECTION_ORDER = [
  "summary", "experience", "education", "projects",
  "skills", "languages", "certifications", "awards",
  "publications", "volunteer", "interests", "references", "custom_sections",
];

// ─── Default Data ─────────────────────────────────────────────────────────────

function makeId() { return Math.random().toString(36).slice(2, 10); }

const DEFAULT_DATA: ResumeData = {
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
};

const DEFAULT_DESIGN: DesignData = {
  primary_color: "#2563eb",
  text_color: "#1a1a1a",
  background_color: "#ffffff",
  font_family: "Inter",
  font_size: 10,
  line_height: 1.4,
  sidebar_width: 35,
  page_format: "Letter",
  margin_x: 36,
  margin_y: 36,
};

const TEMPLATES = [
  { id: "classic", name: "Classic", description: "Traditional serif layout", tags: ["ATS", "Formal", "Single-column"] },
  { id: "modern_tech", name: "Modern Tech", description: "Clean sans-serif for tech roles", tags: ["Tech", "Startup", "Single-column"] },
  { id: "minimal", name: "Minimal", description: "Ultra-clean, no decoration", tags: ["Clean", "Design", "Single-column"] },
  { id: "professional", name: "Professional", description: "Executive serif layout", tags: ["Senior", "Finance", "Single-column"] },
  { id: "ats_safe", name: "ATS Safe", description: "Plain, maximum compatibility", tags: ["ATS", "Enterprise", "Single-column"] },
  { id: "academic", name: "Academic", description: "Education-first layout", tags: ["Research", "PhD", "Single-column"] },
];

const FONTS = [
  "Inter", "Roboto", "Lato", "Open Sans", "Montserrat", "Raleway",
  "Merriweather", "Playfair Display", "PT Serif", "Source Sans Pro",
  "Noto Sans", "Libre Baskerville", "Crimson Text", "Josefin Sans", "Nunito"
];

const FLUENCY_LEVELS = ["Native", "Fluent", "Professional", "Intermediate", "Elementary"];
const NETWORKS = ["LinkedIn", "GitHub", "Twitter", "Portfolio", "Behance", "Dribbble", "Medium", "Dev.to", "YouTube", "GitLab", "Instagram"];

// ─── Section Icons & Labels ───────────────────────────────────────────────────

const SECTION_META: Record<SectionKey, { icon: React.ElementType; label: string }> = {
  photo: { icon: ImageIcon, label: "Picture" },
  basics: { icon: User, label: "Basics" },
  summary: { icon: AlignLeft, label: "Summary" },
  profiles: { icon: Link2, label: "Profiles" },
  experience: { icon: Briefcase, label: "Experience" },
  education: { icon: GraduationCap, label: "Education" },
  projects: { icon: FolderOpen, label: "Projects" },
  skills: { icon: Zap, label: "Skills" },
  languages: { icon: Globe, label: "Languages" },
  awards: { icon: Trophy, label: "Awards" },
  certifications: { icon: Award, label: "Certifications" },
  publications: { icon: BookOpen, label: "Publications" },
  volunteer: { icon: Heart, label: "Volunteer" },
  interests: { icon: Star, label: "Interests" },
  references: { icon: Users, label: "References" },
  custom: { icon: Plus, label: "Custom" },
};

const LEFT_SECTIONS: SectionKey[] = [
  "photo", "basics", "summary", "profiles", "experience", "education",
  "projects", "skills", "languages", "awards", "certifications",
  "publications", "volunteer", "interests", "references", "custom"
];

// ─── Helper Components ────────────────────────────────────────────────────────

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-white/60 uppercase tracking-wide">{label}</label>
      {children}
    </div>
  );
}

function Input({ value, onChange, placeholder, type = "text", className = "" }: any) {
  return (
    <input
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      className={`w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all ${className}`}
    />
  );
}

function Textarea({ value, onChange, placeholder, rows = 4 }: any) {
  return (
    <textarea
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      rows={rows}
      className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all resize-none"
    />
  );
}

function Select({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500/50 transition-all appearance-none"
    >
      {options.map(o => <option key={o} value={o} className="bg-gray-900">{o}</option>)}
    </select>
  );
}

function NumberInput({ value, onChange, min, max, step = 1, suffix = "" }: any) {
  return (
    <div className="flex items-center gap-1">
      <input
        type="number"
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        min={min} max={max} step={step}
        className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500/50 transition-all"
      />
      {suffix && <span className="text-xs text-white/40 whitespace-nowrap">{suffix}</span>}
    </div>
  );
}

function ColorInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="relative">
        <input type="color" value={value} onChange={e => onChange(e.target.value)} className="w-8 h-8 rounded cursor-pointer border border-white/10 bg-transparent p-0.5" />
      </div>
      <Input value={value} onChange={(e: any) => onChange(e.target.value)} placeholder="#000000" className="flex-1" />
    </div>
  );
}

function TagInput({ tags, onChange, placeholder }: { tags: string[]; onChange: (t: string[]) => void; placeholder: string }) {
  const [input, setInput] = useState("");
  const addTag = () => {
    const v = input.trim();
    if (v && !tags.includes(v)) { onChange([...tags, v]); setInput(""); }
  };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {tags.map(t => (
          <span key={t} className="flex items-center gap-1 bg-blue-500/20 text-blue-300 text-xs px-2 py-0.5 rounded-full">
            {t}
            <button onClick={() => onChange(tags.filter(x => x !== t))} className="hover:text-red-400"><X size={10} /></button>
          </span>
        ))}
      </div>
      <div className="flex gap-1">
        <Input value={input} onChange={(e: any) => setInput(e.target.value)} placeholder={placeholder}
          onKeyDown={(e: any) => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }} />
        <button onClick={addTag} className="px-3 py-2 bg-blue-600/30 hover:bg-blue-600/50 rounded-lg text-blue-300 text-sm transition-colors">+</button>
      </div>
    </div>
  );
}

// ─── Section Accordion ────────────────────────────────────────────────────────

function SectionAccordion({ id, sectionKey, children, count }: { id: string; sectionKey: SectionKey; children: React.ReactNode; count?: number }) {
  const [open, setOpen] = useState(false);
  const meta = SECTION_META[sectionKey];
  const Icon = meta.icon;
  return (
    <div id={`sidebar-${id}`} className="border border-white/5 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-4 py-3 bg-white/5 hover:bg-white/8 transition-colors text-left"
      >
        <Icon size={16} className="text-blue-400 shrink-0" />
        <span className="flex-1 text-sm font-medium text-white">{meta.label}</span>
        {count !== undefined && count > 0 && (
          <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded-full">{count}</span>
        )}
        {open ? <ChevronUp size={14} className="text-white/40" /> : <ChevronDown size={14} className="text-white/40" />}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="p-4 space-y-4 border-t border-white/5">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Item Row (for list sections) ────────────────────────────────────────────

function ItemRow({ title, subtitle, hidden, onToggleHide, onEdit, onDelete, onDuplicate, dragHandleProps }: any) {
  return (
    <div className={`flex items-center gap-2 p-2 rounded-lg border border-white/5 hover:border-white/10 bg-white/3 group transition-all ${hidden ? "opacity-50" : ""}`}>
      <div {...dragHandleProps} className="cursor-grab active:cursor-grabbing text-white/20 hover:text-white/50 transition-colors">
        <GripVertical size={14} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-white truncate">{title || <span className="text-white/30">Untitled</span>}</p>
        {subtitle && <p className="text-xs text-white/40 truncate">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button onClick={onToggleHide} className="p-1 hover:bg-white/10 rounded transition-colors" title={hidden ? "Show" : "Hide"}>
          {hidden ? <EyeOff size={12} className="text-white/40" /> : <Eye size={12} className="text-white/60" />}
        </button>
        {onDuplicate && <button onClick={onDuplicate} className="p-1 hover:bg-white/10 rounded transition-colors"><Copy size={12} className="text-white/60" /></button>}
        <button onClick={onEdit} className="p-1 hover:bg-blue-500/20 rounded transition-colors"><Edit3 size={12} className="text-blue-400" /></button>
        <button onClick={onDelete} className="p-1 hover:bg-red-500/20 rounded transition-colors"><Trash2 size={12} className="text-red-400" /></button>
      </div>
    </div>
  );
}

// ─── Item Edit Dialog ─────────────────────────────────────────────────────────

function EditDialog({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-[#0f1117] border border-white/10 rounded-2xl shadow-2xl"
      >
        <div className="flex items-center justify-between p-5 border-b border-white/10 sticky top-0 bg-[#0f1117] z-10">
          <h3 className="text-base font-semibold text-white">{title}</h3>
          <button onClick={onClose} className="p-1.5 hover:bg-white/10 rounded-lg transition-colors"><X size={16} className="text-white/60" /></button>
        </div>
        <div className="p-5 space-y-4">{children}</div>
        <div className="p-5 border-t border-white/10 flex justify-end">
          <button onClick={onClose} className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors">Done</button>
        </div>
      </motion.div>
    </div>
  );
}

// ─── Template Gallery ─────────────────────────────────────────────────────────

function TemplateGallery({ current, onSelect, onClose }: { current: string; onSelect: (id: string) => void; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="relative w-full max-w-3xl max-h-[85vh] bg-[#0f1117] border border-white/10 rounded-2xl shadow-2xl overflow-hidden"
      >
        <div className="flex items-center justify-between p-5 border-b border-white/10">
          <div>
            <h2 className="text-lg font-bold text-white">Template Gallery</h2>
            <p className="text-xs text-white/50 mt-0.5">Choose a template for your resume</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-lg transition-colors"><X size={16} className="text-white/60" /></button>
        </div>
        <div className="p-5 overflow-y-auto max-h-[calc(85vh-80px)] grid grid-cols-3 gap-4">
          {TEMPLATES.map(t => (
            <button
              key={t.id}
              onClick={() => { onSelect(t.id); onClose(); }}
              className={`group text-left border rounded-xl overflow-hidden transition-all hover:scale-[1.02] ${current === t.id ? "border-blue-500 ring-2 ring-blue-500/30" : "border-white/10 hover:border-white/30"}`}
            >
              <div className="bg-white/5 aspect-[3/4] flex items-center justify-center overflow-hidden relative">
                <img
                  src={`/templates/${t.id}.jpg`}
                  alt={t.name}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  onError={(e) => {
                    // Fallback if image fails
                    (e.target as HTMLElement).style.display = 'none';
                  }}
                />
              </div>
              <div className="p-3">
                <p className="text-sm font-semibold text-white">{t.name}</p>
                <p className="text-xs text-white/50 mt-0.5">{t.description}</p>
                <div className="flex flex-wrap gap-1 mt-2">
                  {t.tags.map(tag => (
                    <span key={tag} className="text-[10px] bg-white/5 text-white/40 px-2 py-0.5 rounded-full">{tag}</span>
                  ))}
                </div>
              </div>
              {current === t.id && (
                <div className="absolute top-2 right-2 bg-blue-600 rounded-full p-0.5">
                  <CheckCircle size={12} className="text-white" />
                </div>
              )}
            </button>
          ))}
        </div>
      </motion.div>
    </div>
  );
}

// ─── Main Builder Page ────────────────────────────────────────────────────────

export default function BuilderPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const resumeIdParam = searchParams?.get("id");

  const [data, setData] = useState<ResumeData>(DEFAULT_DATA);
  const [design, setDesign] = useState<DesignData>(DEFAULT_DESIGN);
  const [templateId, setTemplateId] = useState("classic");
  const [resumeId, setResumeId] = useState<string | null>(resumeIdParam);
  const [resumeName, setResumeName] = useState("My Resume");
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [previewHtml, setPreviewHtml] = useState<string>("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [showTemplateGallery, setShowTemplateGallery] = useState(false);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [rightTab, setRightTab] = useState<"design" | "layout" | "analyze">("design");
  const [editDialog, setEditDialog] = useState<{ type: string; index: number; data: any } | null>(null);
  const [undoStack, setUndoStack] = useState<ResumeData[]>([]);
  const [redoStack, setRedoStack] = useState<ResumeData[]>([]);
  // Section order drives both preview and PDF
  const [sectionOrder, setSectionOrder] = useState<string[]>([...DEFAULT_SECTION_ORDER]);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // ─── Analyze panel state ─────────────────────────────────
  const [jobDescription, setJobDescription] = useState("");
  const [atsResult, setAtsResult] = useState<ATSResult | null>(null);
  const [analyzeLoading, setAnalyzeLoading] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<ChangeItem[]>([]);
  const [suggestLoading, setSuggestLoading] = useState(false);
  const [rewritingBullet, setRewritingBullet] = useState<{ sectionType: string; itemIdx: number; bulletIdx: number } | null>(null);
  const [rewriteResult, setRewriteResult] = useState<{ original: string; suggested: string; sectionType: string; itemIdx: number; bulletIdx: number } | null>(null);

  const previewDebounceRef = useRef<NodeJS.Timeout>();
  const saveDebounceRef = useRef<NodeJS.Timeout>();
  const lastUndoTimeRef = useRef<number>(0);
  // Hydration guard: autosave is a no-op until the page has loaded existing data (or decided there is none)
  const hydratedRef = useRef<boolean>(false);
  // Dirty guard: autosave only fires after the user has made an actual edit
  const dirtyRef = useRef<boolean>(false);
  // In-flight create guard: prevents two concurrent first-saves both POSTing with resume_id=null
  const createInFlightRef = useRef<Promise<string> | null>(null);

  // ─── Load existing resume on mount (BUG-01, BUG-02) ────────────────
  useEffect(() => {
    if (!resumeIdParam) {
      // Fresh builder — mark as hydrated immediately so autosave guard doesn't block manual saves
      hydratedRef.current = true;
      return;
    }
    (async () => {
      try {
        const resume = await getResumeById(resumeIdParam);
        const sj = resume.structured_json || {};
        // Hydrate contact / sections from structured_json
        setData(prev => ({
          ...prev,
          contact: {
            name: sj.contact?.name || "",
            headline: sj.contact?.headline || "",
            email: sj.contact?.email || "",
            phone: sj.contact?.phone || "",
            location: sj.contact?.location || "",
            website: sj.contact?.website || "",
            custom_fields: sj.contact?.custom_fields || [],
          },
          photo: sj.photo || prev.photo,
          summary: sj.summary || "",
          profiles: sj.profiles || [],
          experience: sj.experience || [],
          education: sj.education || [],
          projects: sj.projects || [],
          skills: sj.skills || [],
          languages: sj.languages || [],
          awards: sj.awards || [],
          certifications: sj.certifications || [],
          publications: sj.publications || [],
          volunteer: sj.volunteer || [],
          interests: sj.interests || [],
          references: sj.references || [],
          custom_sections: sj.custom_sections || [],
        }));
        if (resume.design_json) setDesign(resume.design_json as any);
        if (resume.builder_template_id) setTemplateId(resume.builder_template_id);
        if (resume.original_filename) setResumeName(resume.original_filename);
        // Restore persisted section order from structured_json
        if (sj.section_order && Array.isArray(sj.section_order)) setSectionOrder(sj.section_order);
      } catch (err) {
        console.error("Failed to load resume:", err);
      } finally {
        hydratedRef.current = true;
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumeIdParam]);

  // ─── Update data with undo tracking ────────────────────────────────
  const updateData = useCallback((updater: (d: ResumeData) => ResumeData) => {
    // Mark as dirty on the first real user edit
    dirtyRef.current = true;
    setData(prev => {
      const now = Date.now();
      if (now - lastUndoTimeRef.current > 500) {
        setUndoStack(stack => [...stack.slice(-49), prev]);
        setRedoStack([]);
        lastUndoTimeRef.current = now;
      }
      return updater(prev);
    });
  }, []);

  const undo = useCallback(() => {
    setUndoStack(stack => {
      if (!stack.length) return stack;
      const prev = stack[stack.length - 1];
      setRedoStack(r => [...r, data]);
      setData(prev);
      return stack.slice(0, -1);
    });
  }, [data]);

  const redo = useCallback(() => {
    setRedoStack(stack => {
      if (!stack.length) return stack;
      const next = stack[stack.length - 1];
      setUndoStack(u => [...u, data]);
      setData(next);
      return stack.slice(0, -1);
    });
  }, [data]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
      if ((e.ctrlKey || e.metaKey) && (e.key === "y" || (e.key === "z" && e.shiftKey))) { e.preventDefault(); redo(); }
      if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); handleSave(); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [undo, redo]);

  // ─── Live preview ────────────────────────────────────────────────────
  const fetchPreview = useCallback(async (d: ResumeData, tid: string, dsg: any, order: string[]) => {
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      // Convert builder data to structured_json format
      const sj = convertToStructuredJson(d);
      // embed section_order so Jinja picks it up
      const sjWithOrder = { ...sj, section_order: order };
      const { html } = await previewResumeHtml(sjWithOrder, tid, undefined, order, dsg);
      setPreviewHtml(html);
    } catch (e: any) {
      console.error("Preview error:", e);
      setPreviewError(e?.message || "Preview failed");
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  useEffect(() => {
    clearTimeout(previewDebounceRef.current);
    previewDebounceRef.current = setTimeout(() => fetchPreview(data, templateId, design, sectionOrder), 400);
    return () => clearTimeout(previewDebounceRef.current);
  }, [data, templateId, design, sectionOrder, fetchPreview]);

  // ─── Auto-save ────────────────────────────────────────────────────────
  const autoSave = useCallback(async (d: ResumeData, tid: string, rid: string | null) => {
    // Don't save until hydration is complete and the user has made at least one edit
    if (!hydratedRef.current || !dirtyRef.current) return;
    setSaveStatus("saving");
    try {
      let effectiveId = rid;
      const sj = convertToStructuredJson(d);
      // Embed section_order in the saved JSON so it round-trips correctly
      const sjWithOrder = { ...sj, section_order: sectionOrder };
      // Idempotent create: if two rapid saves race with rid=null, only one POST /builder-save
      if (!effectiveId) {
        if (!createInFlightRef.current) {
          createInFlightRef.current = builderSave(
            sjWithOrder, design, tid, undefined, sectionOrder, undefined, resumeName
          ).then(r => { setResumeId(r.resume_id); return r.resume_id; });
        }
        effectiveId = await createInFlightRef.current;
      } else {
        await builderSave(sjWithOrder, design, tid, undefined, sectionOrder, effectiveId, resumeName);
      }
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    } catch (e) {
      setSaveStatus("error");
    }
  }, [design, resumeName, sectionOrder]);

  useEffect(() => {
    clearTimeout(saveDebounceRef.current);
    saveDebounceRef.current = setTimeout(() => autoSave(data, templateId, resumeId), 1500);
    return () => clearTimeout(saveDebounceRef.current);
  // Include design, resumeName and sectionOrder so all changes are persisted
  }, [data, templateId, design, resumeName, sectionOrder, autoSave]);

  const handleSave = async () => {
    if (!hydratedRef.current) return;
    // Allow manual save even if no edit was made yet (e.g. switching template)
    dirtyRef.current = true;
    clearTimeout(saveDebounceRef.current);
    await autoSave(data, templateId, resumeId);
  };

  // ─── Convert builder data to structured_json ──────────────────────────
  function convertToStructuredJson(d: ResumeData) {
    return {
      photo: d.photo,
      contact: {
        name: d.contact.name,
        headline: d.contact.headline,
        email: d.contact.email,
        phone: d.contact.phone,
        location: d.contact.location,
        website: d.contact.website,
        custom_fields: d.contact.custom_fields,
        links: d.profiles.filter(p => !p.hidden).map(p => ({ network: p.network, username: p.username, url: p.url })).filter(p => p.url),
      },
      summary: d.summary,
      profiles: d.profiles,
      experience: d.experience.map(e => ({
        id: e.id, hidden: e.hidden,
        company: e.company, position: e.position, title: e.position,
        location: e.location, start_date: e.start_date, end_date: e.end_date,
        url: e.url, bullet_points: e.bullet_points,
      })),
      education: d.education.map(e => ({
        id: e.id, hidden: e.hidden,
        institution: e.institution, degree: e.degree, field: e.field,
        grade: e.grade, cgpa_or_percentage: e.grade,
        location: e.location, graduation_date: e.graduation_date, description: e.description,
      })),
      projects: d.projects.map(p => ({
        id: p.id, hidden: p.hidden,
        name: p.name, technologies: p.technologies, bullets: p.bullets,
        link: p.url, url: p.url, date: p.period, period: p.period,
      })),
      skills: d.skills.map(s => ({ id: s.id, name: s.name, level: s.level, keywords: s.keywords, hidden: s.hidden })),
      certifications: d.certifications.map(c => ({ id: c.id, title: c.title, issuer: c.issuer, date: c.date, url: c.url, description: c.description, hidden: c.hidden })),
      languages: d.languages.map(l => ({ id: l.id, language: l.language, fluency: l.fluency, level: l.level, hidden: l.hidden })),
      awards: d.awards.map(a => ({ id: a.id, title: a.title, awarder: a.awarder, date: a.date, description: a.description, hidden: a.hidden })),
      publications: d.publications.map(p => ({ id: p.id, title: p.title, publisher: p.publisher, date: p.date, url: p.url, summary: p.summary, hidden: p.hidden })),
      volunteer: d.volunteer.map(v => ({ id: v.id, organization: v.organization, position: v.position, location: v.location, period: v.period, description: v.description, hidden: v.hidden })),
      interests: d.interests.map(i => ({ id: i.id, name: i.name, keywords: i.keywords, hidden: i.hidden })),
      references: d.references.map(r => ({ id: r.id, name: r.name, position: r.position, phone: r.phone, url: r.url, description: r.description, hidden: r.hidden })),
      custom_sections: d.custom_sections.map(c => ({ id: c.id, name: c.name, hidden: c.hidden, items: c.items })),
    };
  }

  // ─── Download PDF ──────────────────────────────────────────────────────
  const handleDownload = async () => {
    setSaveStatus("saving");
    try {
      const sj = convertToStructuredJson(data);
      const sjWithOrder = { ...sj, section_order: sectionOrder };
      await builderDownloadPdf(sjWithOrder, templateId, sectionOrder, design, resumeName);
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    } catch (e: any) {
      console.error("Download failed:", e);
      setSaveStatus("error");
      setPreviewError(e?.message || "PDF download failed — please try again");
    }
  };

  // ─── Analyze handlers ─────────────────────────────────
  const runAnalyze = async () => {
    if (!resumeId && !data.contact.name) {
      setAnalyzeError("Please add your name first, or save the resume.");
      return;
    }
    setAnalyzeLoading(true);
    setAnalyzeError(null);
    setAtsResult(null);
    try {
      // If we have a saved resumeId use it; otherwise save first
      let rid = resumeId;
      if (!rid) {
        dirtyRef.current = true;
        await handleSave();
        rid = resumeId;
      }
      if (!rid) throw new Error("Could not save resume before analysis");
      const result = await analyzeATS(rid, jobDescription || undefined);
      setAtsResult(result);
    } catch (e: any) {
      setAnalyzeError(e?.message || "Analysis failed");
    } finally {
      setAnalyzeLoading(false);
    }
  };

  const runSuggest = async () => {
    if (!resumeId) { setAnalyzeError("Save the resume first."); return; }
    setSuggestLoading(true);
    try {
      const result = await improvePropose(resumeId, "auto_improve", undefined, jobDescription || undefined);
      setSuggestions(result.proposed_changes || []);
    } catch (e: any) {
      setAnalyzeError(e?.message || "Suggestions failed");
    } finally {
      setSuggestLoading(false);
    }
  };

  const runBulletRewrite = async (bulletText: string, sectionType: string, itemIdx: number, bulletIdx: number) => {
    setRewritingBullet({ sectionType, itemIdx, bulletIdx });
    try {
      const result = await improveBullet(bulletText, jobDescription || undefined);
      setRewriteResult({ original: bulletText, suggested: result.suggested, sectionType, itemIdx, bulletIdx });
    } catch (e: any) {
      setAnalyzeError(e?.message || "Rewrite failed");
    } finally {
      setRewritingBullet(null);
    }
  };

  const acceptBulletRewrite = () => {
    if (!rewriteResult) return;
    const { sectionType, itemIdx, bulletIdx, suggested } = rewriteResult;
    updateData(d => {
      const arr = [...(d as any)[sectionType]];
      const item = { ...arr[itemIdx] };
      const bullets = [...(item.bullet_points || item.bullets || [])];
      bullets[bulletIdx] = suggested;
      if (item.bullet_points !== undefined) item.bullet_points = bullets;
      else item.bullets = bullets;
      arr[itemIdx] = item;
      return { ...d, [sectionType]: arr };
    });
    setRewriteResult(null);
  };

  // ─── Section helpers ──────────────────────────────────────────────────
  const toggleHide = (section: keyof ResumeData, index: number) => {
    updateData(d => {
      const arr = [...(d[section] as any[])];
      arr[index] = { ...arr[index], hidden: !arr[index].hidden };
      return { ...d, [section]: arr };
    });
  };

  const deleteItem = (section: keyof ResumeData, index: number) => {
    updateData(d => {
      const arr = [...(d[section] as any[])];
      arr.splice(index, 1);
      return { ...d, [section]: arr };
    });
  };

  const updateItem = (section: keyof ResumeData, index: number, item: any) => {
    updateData(d => {
      const arr = [...(d[section] as any[])];
      arr[index] = { ...arr[index], ...item };
      return { ...d, [section]: arr };
    });
  };

  const addItem = (section: keyof ResumeData, item: any) => {
    updateData(d => ({ ...d, [section]: [...(d[section] as any[]), { id: makeId(), hidden: false, ...item }] }));
  };

  return (
    <div className="fixed inset-0 bg-[#080c14] flex flex-col z-50">
      {/* Mobile warning — builder requires a larger screen */}
      <div className="md:hidden fixed inset-0 z-[100] bg-[#080c14] flex flex-col items-center justify-center p-8 text-center">
        <FileText size={48} className="text-white/20 mb-4" />
        <h2 className="text-white text-xl font-semibold mb-2">Builder needs a larger screen</h2>
        <p className="text-white/50 text-sm leading-relaxed mb-6">The resume builder is optimised for desktop use. Please open it on a screen wider than 768 px.</p>
        <button onClick={() => router.push("/")} className="px-4 py-2 bg-blue-600 rounded-lg text-white text-sm font-medium hover:bg-blue-700 transition-colors">
          Back to Dashboard
        </button>
      </div>

      {/* Header */}
      <header role="banner" className="h-14 flex items-center gap-3 px-4 border-b border-white/5 bg-[#0a0f1a]/80 backdrop-blur-sm shrink-0 z-30">
        <button
          onClick={() => router.push("/")}
          aria-label="Back to dashboard"
          className="p-2 hover:bg-white/5 rounded-lg transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500"
        >
          <ArrowLeft size={16} className="text-white/60" aria-hidden="true" />
        </button>

        <div className="flex items-center gap-2">
          <input
            value={resumeName}
            onChange={e => { setResumeName(e.target.value); dirtyRef.current = true; }}
            aria-label="Resume name"
            title="Resume name — click to rename"
            className="bg-transparent text-sm font-semibold text-white border-none outline-none focus:bg-white/5 focus-visible:ring-1 focus-visible:ring-blue-500 px-2 py-1 rounded-lg transition-colors min-w-0 max-w-[200px]"
          />
        </div>

        {/* My Resumes link */}
        <button
          onClick={() => router.push("/resume")}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-xs text-white/60 transition-colors"
          title="Back to Resume Library"
        >
          <FileText size={12} /> My Resumes
        </button>

        <div className="flex items-center gap-1.5 ml-2">
          {saveStatus === "saving" && <><Loader2 size={12} className="text-white/40 animate-spin" /><span className="text-xs text-white/40">Saving...</span></>}
          {saveStatus === "saved" && <><CheckCircle size={12} className="text-green-400" /><span className="text-xs text-green-400">Saved</span></>}
          {saveStatus === "error" && <span className="text-xs text-red-400">Save failed</span>}
        </div>

        <div className="flex-1" />

        {/* Undo/Redo */}
        <div className="flex items-center gap-1">
          <button onClick={undo} disabled={!undoStack.length} className="p-2 hover:bg-white/5 rounded-lg transition-colors disabled:opacity-30" title="Undo (Ctrl+Z)">
            <RotateCcw size={14} className="text-white/60" />
          </button>
          <button onClick={redo} disabled={!redoStack.length} className="p-2 hover:bg-white/5 rounded-lg transition-colors disabled:opacity-30" title="Redo (Ctrl+Y)">
            <RotateCw size={14} className="text-white/60" />
          </button>
        </div>

        {/* Panel toggles */}
        <button onClick={() => setLeftOpen(!leftOpen)} className="p-2 hover:bg-white/5 rounded-lg transition-colors" title="Toggle left panel">
          {leftOpen ? <PanelLeftClose size={14} className="text-white/60" /> : <PanelLeftOpen size={14} className="text-white/60" />}
        </button>
        <button onClick={() => setRightOpen(!rightOpen)} className="p-2 hover:bg-white/5 rounded-lg transition-colors" title="Toggle right panel">
          {rightOpen ? <PanelRightClose size={14} className="text-white/60" /> : <PanelRightOpen size={14} className="text-white/60" />}
        </button>

        <button onClick={handleSave} className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-sm text-white/80 transition-colors">
          <Save size={13} /> Save
        </button>
        {/* Split Download group */}
        <div className="flex items-center">
          <button
            onClick={handleDownload}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-l-lg text-sm font-medium text-white transition-colors"
          >
            <Download size={13} /> PDF
          </button>
          <button
            onClick={async () => {
              // DOCX: save first if no ID, then open download URL
              if (!resumeId) { dirtyRef.current = true; await handleSave(); }
              const rid = resumeId;
              if (rid) window.open(`${API_BASE}/resumes/${rid}/docx`, "_blank");
            }}
            title="Download DOCX"
            className="flex items-center gap-1 px-2 py-1.5 bg-blue-700 hover:bg-blue-800 border-l border-blue-500/40 rounded-r-lg text-sm text-white transition-colors"
          >
            <FileText size={13} /> DOCX
          </button>
        </div>
      </header>

      {/* Main 3-panel layout */}
      <div className="flex-1 flex overflow-hidden">
        <PanelGroup autoSave="builder-panels" orientation="horizontal">
          {/* LEFT PANEL — Content Editor */}
          {leftOpen && (
            <>
              <Panel defaultSize={25} className="flex flex-col min-w-0">
                <div className="h-full flex">
                  {/* Icon rail */}
                  <div className="w-12 shrink-0 flex flex-col items-center gap-1 py-3 border-r border-white/5 bg-[#0a0f1a]">
                    {LEFT_SECTIONS.map(s => {
                      const Icon = SECTION_META[s].icon;
                      return (
                        <button
                          key={s}
                          title={SECTION_META[s].label}
                          onClick={() => document.getElementById(`sidebar-${s}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}
                          className="p-2 hover:bg-white/5 rounded-lg transition-colors"
                        >
                          <Icon size={14} className="text-white/40 hover:text-white/80 transition-colors" />
                        </button>
                      );
                    })}
                  </div>

                  {/* Scrollable sections */}
                  <div className="flex-1 overflow-y-auto p-3 space-y-2">
                    {/* PICTURE */}
                    <SectionAccordion id="photo" sectionKey="photo">
                      <FormField label="Photo URL or upload">
                        <div className="flex gap-2">
                          <Input value={data.photo.url} onChange={(e: any) => updateData(d => ({ ...d, photo: { ...d.photo, url: e.target.value } }))} placeholder="https://... or upload below" />
                          <button onClick={() => document.getElementById("avatar-upload")?.click()} className="px-3 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-xs text-white/60 whitespace-nowrap transition-colors">
                            Upload
                          </button>
                          <input id="avatar-upload" type="file" accept="image/*" className="hidden" onChange={async e => {
                            const file = e.target.files?.[0];
                            if (!file) return;
                            const { url } = await uploadAvatar(file);
                            updateData(d => ({ ...d, photo: { ...d.photo, url } }));
                          }} />
                        </div>
                      </FormField>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-white/50">Visible in resume</span>
                        <button
                          onClick={() => updateData(d => ({ ...d, photo: { ...d.photo, hidden: !d.photo.hidden } }))}
                          className="flex items-center gap-1 text-xs text-white/50 hover:text-white transition-colors"
                        >
                          {data.photo.hidden ? <><EyeOff size={12} /> Hidden</> : <><Eye size={12} /> Visible</>}
                        </button>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <FormField label="Size (pt)"><NumberInput value={data.photo.size} onChange={(v: number) => updateData(d => ({ ...d, photo: { ...d.photo, size: v } }))} min={32} max={200} /></FormField>
                        <FormField label="Border Radius">
                          <div className="space-y-1">
                            <NumberInput value={data.photo.border_radius} onChange={(v: number) => updateData(d => ({ ...d, photo: { ...d.photo, border_radius: v } }))} min={0} max={100} suffix="%" />
                            <div className="flex gap-1">
                              {[0, 10, 50].map(v => { const active = data.photo.border_radius === v; const cls = "flex-1 py-1 text-xs rounded border transition-colors " + (active ? "border-blue-500 text-blue-400" : "border-white/10 text-white/40"); return <button key={v} onClick={() => updateData(d => ({ ...d, photo: { ...d.photo, border_radius: v } }))} className={cls}>{v === 0 ? "S" : v === 10 ? "R" : "C"}</button>; })}
                            </div>
                          </div>
                        </FormField>
                        <FormField label="Border Width"><NumberInput value={data.photo.border_width} onChange={(v: number) => updateData(d => ({ ...d, photo: { ...d.photo, border_width: v } }))} min={0} max={10} suffix="pt" /></FormField>
                        <FormField label="Border Color"><ColorInput value={data.photo.border_color} onChange={v => updateData(d => ({ ...d, photo: { ...d.photo, border_color: v } }))} label="Border" /></FormField>
                      </div>
                    </SectionAccordion>

                    {/* BASICS */}
                    <SectionAccordion id="basics" sectionKey="basics">
                      <FormField label="Full Name"><Input value={data.contact.name} onChange={(e: any) => updateData(d => ({ ...d, contact: { ...d.contact, name: e.target.value } }))} placeholder="Your Name" /></FormField>
                      <FormField label="Headline / Title"><Input value={data.contact.headline} onChange={(e: any) => updateData(d => ({ ...d, contact: { ...d.contact, headline: e.target.value } }))} placeholder="Software Engineer" /></FormField>
                      <FormField label="Email"><Input value={data.contact.email} onChange={(e: any) => updateData(d => ({ ...d, contact: { ...d.contact, email: e.target.value } }))} placeholder="you@email.com" type="email" /></FormField>
                      <FormField label="Phone"><Input value={data.contact.phone} onChange={(e: any) => updateData(d => ({ ...d, contact: { ...d.contact, phone: e.target.value } }))} placeholder="+91 9876543210" /></FormField>
                      <FormField label="Location"><Input value={data.contact.location} onChange={(e: any) => updateData(d => ({ ...d, contact: { ...d.contact, location: e.target.value } }))} placeholder="City, Country" /></FormField>
                      <FormField label="Website"><Input value={data.contact.website} onChange={(e: any) => updateData(d => ({ ...d, contact: { ...d.contact, website: e.target.value } }))} placeholder="https://portfolio.dev" /></FormField>
                    </SectionAccordion>

                    {/* SUMMARY */}
                    <SectionAccordion id="summary" sectionKey="summary">
                      <FormField label="Professional Summary">
                        <Textarea value={data.summary} onChange={(e: any) => updateData(d => ({ ...d, summary: e.target.value }))} placeholder="Write a compelling professional summary..." rows={5} />
                      </FormField>
                    </SectionAccordion>

                    {/* PROFILES */}
                    <SectionAccordion id="profiles" sectionKey="profiles" count={data.profiles.length}>
                      <Reorder.Group axis="y" values={data.profiles} onReorder={items => updateData(d => ({ ...d, profiles: items }))}>
                        {data.profiles.map((p, i) => (
                          <Reorder.Item key={p.id} value={p}>
                            <ItemRow
                              title={p.network} subtitle={p.username}
                              hidden={p.hidden}
                              onToggleHide={() => toggleHide("profiles", i)}
                              onEdit={() => setEditDialog({ type: "profiles", index: i, data: { ...p } })}
                              onDelete={() => deleteItem("profiles", i)}
                              dragHandleProps={{}}
                            />
                          </Reorder.Item>
                        ))}
                      </Reorder.Group>
                      <button onClick={() => addItem("profiles", { network: "LinkedIn", username: "", url: "" })} className="w-full flex items-center gap-2 py-2 px-3 border border-dashed border-white/20 hover:border-white/40 rounded-lg text-sm text-white/40 hover:text-white/60 transition-all">
                        <Plus size={14} /> Add Profile
                      </button>
                    </SectionAccordion>

                    {/* EXPERIENCE */}
                    <SectionAccordion id="experience" sectionKey="experience" count={data.experience.length}>
                      <Reorder.Group axis="y" values={data.experience} onReorder={items => updateData(d => ({ ...d, experience: items }))}>
                        {data.experience.map((e, i) => (
                          <Reorder.Item key={e.id} value={e}>
                            <ItemRow title={e.company} subtitle={e.position} hidden={e.hidden} onToggleHide={() => toggleHide("experience", i)} onEdit={() => setEditDialog({ type: "experience", index: i, data: { ...e } })} onDelete={() => deleteItem("experience", i)} onDuplicate={() => addItem("experience", { ...e, id: makeId() })} dragHandleProps={{}} />
                          </Reorder.Item>
                        ))}
                      </Reorder.Group>
                      <button onClick={() => addItem("experience", { company: "", position: "", location: "", start_date: "", end_date: "", url: "", bullet_points: [] })} className="w-full flex items-center gap-2 py-2 px-3 border border-dashed border-white/20 hover:border-white/40 rounded-lg text-sm text-white/40 hover:text-white/60 transition-all">
                        <Plus size={14} /> Add Experience
                      </button>
                    </SectionAccordion>

                    {/* EDUCATION */}
                    <SectionAccordion id="education" sectionKey="education" count={data.education.length}>
                      <Reorder.Group axis="y" values={data.education} onReorder={items => updateData(d => ({ ...d, education: items }))}>
                        {data.education.map((e, i) => (
                          <Reorder.Item key={e.id} value={e}>
                            <ItemRow title={e.institution} subtitle={e.degree} hidden={e.hidden} onToggleHide={() => toggleHide("education", i)} onEdit={() => setEditDialog({ type: "education", index: i, data: { ...e } })} onDelete={() => deleteItem("education", i)} dragHandleProps={{}} />
                          </Reorder.Item>
                        ))}
                      </Reorder.Group>
                      <button onClick={() => addItem("education", { institution: "", degree: "", field: "", grade: "", location: "", graduation_date: "", description: "" })} className="w-full flex items-center gap-2 py-2 px-3 border border-dashed border-white/20 hover:border-white/40 rounded-lg text-sm text-white/40 hover:text-white/60 transition-all">
                        <Plus size={14} /> Add Education
                      </button>
                    </SectionAccordion>

                    {/* PROJECTS */}
                    <SectionAccordion id="projects" sectionKey="projects" count={data.projects.length}>
                      <Reorder.Group axis="y" values={data.projects} onReorder={items => updateData(d => ({ ...d, projects: items }))}>
                        {data.projects.map((p, i) => (
                          <Reorder.Item key={p.id} value={p}>
                            <ItemRow title={p.name} subtitle={p.technologies.slice(0, 3).join(", ")} hidden={p.hidden} onToggleHide={() => toggleHide("projects", i)} onEdit={() => setEditDialog({ type: "projects", index: i, data: { ...p } })} onDelete={() => deleteItem("projects", i)} dragHandleProps={{}} />
                          </Reorder.Item>
                        ))}
                      </Reorder.Group>
                      <button onClick={() => addItem("projects", { name: "", period: "", url: "", technologies: [], bullets: [] })} className="w-full flex items-center gap-2 py-2 px-3 border border-dashed border-white/20 hover:border-white/40 rounded-lg text-sm text-white/40 hover:text-white/60 transition-all">
                        <Plus size={14} /> Add Project
                      </button>
                    </SectionAccordion>

                    {/* SKILLS */}
                    <SectionAccordion id="skills" sectionKey="skills" count={data.skills.length}>
                      <Reorder.Group axis="y" values={data.skills} onReorder={items => updateData(d => ({ ...d, skills: items }))}>
                        {data.skills.map((s, i) => (
                          <Reorder.Item key={s.id} value={s}>
                            <ItemRow title={s.name} subtitle={s.level > 0 ? `Level ${s.level}/5` : undefined} hidden={s.hidden} onToggleHide={() => toggleHide("skills", i)} onEdit={() => setEditDialog({ type: "skills", index: i, data: { ...s } })} onDelete={() => deleteItem("skills", i)} dragHandleProps={{}} />
                          </Reorder.Item>
                        ))}
                      </Reorder.Group>
                      <button onClick={() => addItem("skills", { name: "", level: 0, keywords: [] })} className="w-full flex items-center gap-2 py-2 px-3 border border-dashed border-white/20 hover:border-white/40 rounded-lg text-sm text-white/40 hover:text-white/60 transition-all">
                        <Plus size={14} /> Add Skill
                      </button>
                    </SectionAccordion>

                    {/* LANGUAGES */}
                    <SectionAccordion id="languages" sectionKey="languages" count={data.languages.length}>
                      <Reorder.Group axis="y" values={data.languages} onReorder={items => updateData(d => ({ ...d, languages: items }))}>
                        {data.languages.map((l, i) => (
                          <Reorder.Item key={l.id} value={l}>
                            <ItemRow title={l.language} subtitle={l.fluency} hidden={l.hidden} onToggleHide={() => toggleHide("languages", i)} onEdit={() => setEditDialog({ type: "languages", index: i, data: { ...l } })} onDelete={() => deleteItem("languages", i)} dragHandleProps={{}} />
                          </Reorder.Item>
                        ))}
                      </Reorder.Group>
                      <button onClick={() => addItem("languages", { language: "", fluency: "Professional", level: 3 })} className="w-full flex items-center gap-2 py-2 px-3 border border-dashed border-white/20 hover:border-white/40 rounded-lg text-sm text-white/40 hover:text-white/60 transition-all">
                        <Plus size={14} /> Add Language
                      </button>
                    </SectionAccordion>

                    {/* AWARDS */}
                    <SectionAccordion id="awards" sectionKey="awards" count={data.awards.length}>
                      <Reorder.Group axis="y" values={data.awards} onReorder={items => updateData(d => ({ ...d, awards: items }))}>
                        {data.awards.map((a, i) => (
                          <Reorder.Item key={a.id} value={a}>
                            <ItemRow title={a.title} subtitle={a.awarder} hidden={a.hidden} onToggleHide={() => toggleHide("awards", i)} onEdit={() => setEditDialog({ type: "awards", index: i, data: { ...a } })} onDelete={() => deleteItem("awards", i)} dragHandleProps={{}} />
                          </Reorder.Item>
                        ))}
                      </Reorder.Group>
                      <button onClick={() => addItem("awards", { title: "", awarder: "", date: "", description: "" })} className="w-full flex items-center gap-2 py-2 px-3 border border-dashed border-white/20 hover:border-white/40 rounded-lg text-sm text-white/40 hover:text-white/60 transition-all">
                        <Plus size={14} /> Add Award
                      </button>
                    </SectionAccordion>

                    {/* CERTIFICATIONS */}
                    <SectionAccordion id="certifications" sectionKey="certifications" count={data.certifications.length}>
                      <Reorder.Group axis="y" values={data.certifications} onReorder={items => updateData(d => ({ ...d, certifications: items }))}>
                        {data.certifications.map((c, i) => (
                          <Reorder.Item key={c.id} value={c}>
                            <ItemRow title={c.title} subtitle={c.issuer} hidden={c.hidden} onToggleHide={() => toggleHide("certifications", i)} onEdit={() => setEditDialog({ type: "certifications", index: i, data: { ...c } })} onDelete={() => deleteItem("certifications", i)} dragHandleProps={{}} />
                          </Reorder.Item>
                        ))}
                      </Reorder.Group>
                      <button onClick={() => addItem("certifications", { title: "", issuer: "", date: "", url: "", description: "" })} className="w-full flex items-center gap-2 py-2 px-3 border border-dashed border-white/20 hover:border-white/40 rounded-lg text-sm text-white/40 hover:text-white/60 transition-all">
                        <Plus size={14} /> Add Certification
                      </button>
                    </SectionAccordion>

                    {/* PUBLICATIONS */}
                    <SectionAccordion id="publications" sectionKey="publications" count={data.publications.length}>
                      <Reorder.Group axis="y" values={data.publications} onReorder={items => updateData(d => ({ ...d, publications: items }))}>
                        {data.publications.map((p, i) => (
                          <Reorder.Item key={p.id} value={p}>
                            <ItemRow title={p.title} subtitle={p.publisher} hidden={p.hidden} onToggleHide={() => toggleHide("publications", i)} onEdit={() => setEditDialog({ type: "publications", index: i, data: { ...p } })} onDelete={() => deleteItem("publications", i)} dragHandleProps={{}} />
                          </Reorder.Item>
                        ))}
                      </Reorder.Group>
                      <button onClick={() => addItem("publications", { title: "", publisher: "", date: "", url: "", summary: "" })} className="w-full flex items-center gap-2 py-2 px-3 border border-dashed border-white/20 hover:border-white/40 rounded-lg text-sm text-white/40 hover:text-white/60 transition-all">
                        <Plus size={14} /> Add Publication
                      </button>
                    </SectionAccordion>

                    {/* VOLUNTEER */}
                    <SectionAccordion id="volunteer" sectionKey="volunteer" count={data.volunteer.length}>
                      <Reorder.Group axis="y" values={data.volunteer} onReorder={items => updateData(d => ({ ...d, volunteer: items }))}>
                        {data.volunteer.map((v, i) => (
                          <Reorder.Item key={v.id} value={v}>
                            <ItemRow title={v.organization} subtitle={v.position} hidden={v.hidden} onToggleHide={() => toggleHide("volunteer", i)} onEdit={() => setEditDialog({ type: "volunteer", index: i, data: { ...v } })} onDelete={() => deleteItem("volunteer", i)} dragHandleProps={{}} />
                          </Reorder.Item>
                        ))}
                      </Reorder.Group>
                      <button onClick={() => addItem("volunteer", { organization: "", position: "", location: "", period: "", description: "" })} className="w-full flex items-center gap-2 py-2 px-3 border border-dashed border-white/20 hover:border-white/40 rounded-lg text-sm text-white/40 hover:text-white/60 transition-all">
                        <Plus size={14} /> Add Volunteer
                      </button>
                    </SectionAccordion>

                    {/* INTERESTS */}
                    <SectionAccordion id="interests" sectionKey="interests" count={data.interests.length}>
                      <Reorder.Group axis="y" values={data.interests} onReorder={items => updateData(d => ({ ...d, interests: items }))}>
                        {data.interests.map((it, i) => (
                          <Reorder.Item key={it.id} value={it}>
                            <ItemRow title={it.name} subtitle={it.keywords.join(", ")} hidden={it.hidden} onToggleHide={() => toggleHide("interests", i)} onEdit={() => setEditDialog({ type: "interests", index: i, data: { ...it } })} onDelete={() => deleteItem("interests", i)} dragHandleProps={{}} />
                          </Reorder.Item>
                        ))}
                      </Reorder.Group>
                      <button onClick={() => addItem("interests", { name: "", keywords: [] })} className="w-full flex items-center gap-2 py-2 px-3 border border-dashed border-white/20 hover:border-white/40 rounded-lg text-sm text-white/40 hover:text-white/60 transition-all">
                        <Plus size={14} /> Add Interest
                      </button>
                    </SectionAccordion>

                    {/* REFERENCES */}
                    <SectionAccordion id="references" sectionKey="references" count={data.references.length}>
                      <Reorder.Group axis="y" values={data.references} onReorder={items => updateData(d => ({ ...d, references: items }))}>
                        {data.references.map((r, i) => (
                          <Reorder.Item key={r.id} value={r}>
                            <ItemRow title={r.name} subtitle={r.position} hidden={r.hidden} onToggleHide={() => toggleHide("references", i)} onEdit={() => setEditDialog({ type: "references", index: i, data: { ...r } })} onDelete={() => deleteItem("references", i)} dragHandleProps={{}} />
                          </Reorder.Item>
                        ))}
                      </Reorder.Group>
                      <button onClick={() => addItem("references", { name: "", position: "", phone: "", url: "", description: "" })} className="w-full flex items-center gap-2 py-2 px-3 border border-dashed border-white/20 hover:border-white/40 rounded-lg text-sm text-white/40 hover:text-white/60 transition-all">
                        <Plus size={14} /> Add Reference
                      </button>
                    </SectionAccordion>

                    {/* CUSTOM SECTIONS */}
                    <SectionAccordion id="custom" sectionKey="custom" count={data.custom_sections.length}>
                      {data.custom_sections.map((cs, ci) => (
                        <div key={cs.id} className="border border-white/10 rounded-xl overflow-hidden mb-2">
                          <div className="flex items-center gap-2 px-3 py-2 bg-white/3">
                            <span className="text-sm text-white flex-1">{cs.name}</span>
                            <button onClick={() => updateData(d => { const arr = [...d.custom_sections]; arr[ci] = { ...arr[ci], hidden: !arr[ci].hidden }; return { ...d, custom_sections: arr }; })} className="p-1 hover:bg-white/10 rounded">
                              {cs.hidden ? <EyeOff size={12} className="text-white/40" /> : <Eye size={12} className="text-white/60" />}
                            </button>
                            <button onClick={() => updateData(d => { const arr = [...d.custom_sections]; arr.splice(ci, 1); return { ...d, custom_sections: arr }; })} className="p-1 hover:bg-red-500/20 rounded"><Trash2 size={12} className="text-red-400" /></button>
                          </div>
                          <div className="p-2 space-y-1">
                            {cs.items.map((item, ii) => (
                              <ItemRow key={item.id} title={item.title} subtitle={item.subtitle} hidden={item.hidden}
                                onToggleHide={() => updateData(d => { const arr = [...d.custom_sections]; arr[ci].items[ii].hidden = !arr[ci].items[ii].hidden; return { ...d, custom_sections: arr }; })}
                                onEdit={() => setEditDialog({ type: "custom_item", index: ii, data: { sectionIndex: ci, item: { ...item } } })}
                                onDelete={() => updateData(d => { const arr = [...d.custom_sections]; arr[ci].items.splice(ii, 1); return { ...d, custom_sections: arr }; })}
                                dragHandleProps={{}}
                              />
                            ))}
                            <button onClick={() => updateData(d => { const arr = [...d.custom_sections]; arr[ci].items.push({ id: makeId(), title: "", subtitle: "", date: "", bullets: [], hidden: false }); return { ...d, custom_sections: arr }; })} className="w-full flex items-center gap-2 py-1.5 px-3 border border-dashed border-white/15 hover:border-white/30 rounded-lg text-xs text-white/40 hover:text-white/60 transition-all">
                              <Plus size={12} /> Add Item
                            </button>
                          </div>
                        </div>
                      ))}
                      <button onClick={() => {
                        const name = prompt("Section name (e.g. Patents, Speaking, Awards):");
                        if (name) updateData(d => ({ ...d, custom_sections: [...d.custom_sections, { id: makeId(), name, items: [], hidden: false }] }));
                      }} className="w-full flex items-center gap-2 py-2 px-3 border border-dashed border-white/20 hover:border-white/40 rounded-lg text-sm text-white/40 hover:text-white/60 transition-all">
                        <Plus size={14} /> Add Custom Section
                      </button>
                    </SectionAccordion>

                    <div className="h-16" />
                  </div>
                </div>
              </Panel>
              <PanelResizeHandle className="w-1 bg-white/5 hover:bg-blue-500/30 transition-colors cursor-col-resize" />
            </>
          )}

          {/* CENTER PANEL — Live Preview */}
          <Panel defaultSize={50} className="relative bg-[#0c1018]">
            <div className="absolute inset-0 overflow-hidden">
              <TransformWrapper
                initialScale={0.6}
                minScale={0.2}
                maxScale={2}
                limitToBounds={false}
                centerOnInit={true}
                wheel={{ step: 0.05 }}
              >
                {({ zoomIn, zoomOut, resetTransform }) => (
                  <>
                    <TransformComponent wrapperStyle={{ width: "100%", height: "100%" }}>
                      <div className="relative" style={{ width: 816, height: 1056 }}>
                        {/* Preview skeleton while loading first time */}
                        {!previewHtml && previewLoading && (
                          <div className="w-full h-full bg-white shadow-2xl flex flex-col p-12 gap-4 animate-pulse">
                            <div className="h-6 bg-gray-200 rounded w-1/3 mx-auto" />
                            <div className="h-3 bg-gray-100 rounded w-1/2 mx-auto" />
                            <div className="h-px bg-gray-200 w-full mt-2" />
                            <div className="h-4 bg-gray-200 rounded w-1/4 mt-4" />
                            {[1,2,3].map(i => <div key={i} className="h-3 bg-gray-100 rounded w-full" />)}
                            <div className="h-4 bg-gray-200 rounded w-1/4 mt-4" />
                            {[1,2,3,4].map(i => <div key={i} className="h-3 bg-gray-100 rounded w-full" />)}
                          </div>
                        )}
                        {/* Error toast overlay */}
                        {previewError && (
                          <div className="absolute bottom-4 left-4 right-4 bg-red-900/90 border border-red-500/50 rounded-lg p-3 z-10">
                            <p className="text-xs text-red-300 font-mono truncate">⚠ Preview error: {previewError}</p>
                            <button onClick={() => setPreviewError(null)} className="absolute top-2 right-2 text-red-400 hover:text-red-200"><X size={12} /></button>
                          </div>
                        )}
                        {previewHtml ? (
                          <iframe
                            srcDoc={previewHtml}
                            className="w-full h-full border-0 shadow-2xl"
                            style={{ background: "white", display: "block" }}
                            title="Resume Preview"
                          />
                        ) : (
                          !previewLoading && (
                            <div className="w-full h-full bg-white flex items-center justify-center shadow-2xl">
                              <div className="text-center text-gray-400">
                                <FileText size={48} className="mx-auto mb-3 opacity-20" />
                                <p className="text-sm">Start filling in your details to see a live preview</p>
                              </div>
                            </div>
                          )
                        )}
                        {/* Spinner overlay on reload */}
                        {previewHtml && previewLoading && (
                          <div className="absolute top-3 right-3 bg-white/80 rounded-full p-1.5 shadow">
                            <Loader2 size={14} className="animate-spin text-blue-500" />
                          </div>
                        )}
                      </div>
                    </TransformComponent>

                    {/* Zoom controls dock */}
                    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1 bg-[#0f1117]/90 backdrop-blur-sm border border-white/10 rounded-xl px-2 py-1.5 shadow-lg">
                      <button onClick={() => zoomOut()} className="p-1.5 hover:bg-white/10 rounded-lg transition-colors"><ZoomOut size={14} className="text-white/60" /></button>
                      <button onClick={() => resetTransform()} className="px-3 py-1 text-xs text-white/50 hover:text-white transition-colors">Reset</button>
                      <button onClick={() => zoomIn()} className="p-1.5 hover:bg-white/10 rounded-lg transition-colors"><ZoomIn size={14} className="text-white/60" /></button>
                      <div className="w-px h-4 bg-white/10 mx-1" />
                      <button onClick={() => setShowTemplateGallery(true)} className="flex items-center gap-1.5 px-2 py-1 hover:bg-white/10 rounded-lg text-xs text-white/50 hover:text-white transition-colors">
                        <Layers size={12} /> {TEMPLATES.find(t => t.id === templateId)?.name}
                      </button>
                    </div>
                  </>
                )}
              </TransformWrapper>
            </div>
          </Panel>

          {/* RIGHT PANEL — Design Controls */}
          {rightOpen && (
            <>
              <PanelResizeHandle className="w-1 bg-white/5 hover:bg-blue-500/30 transition-colors cursor-col-resize" />
              <Panel defaultSize={25} className="flex flex-col min-w-0 bg-[#0a0f1a]">
                {/* Tab bar */}
                <div className="flex border-b border-white/5 shrink-0">
                  {[
                    { k: "design", icon: Palette, label: "Design" },
                    { k: "layout", icon: Layout, label: "Layout" },
                    { k: "analyze", icon: Sparkles, label: "Analyze" },
                  ].map(({ k, icon: Icon, label }) => (
                    <button key={k} onClick={() => setRightTab(k as any)} className={`flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium transition-colors border-b-2 ${rightTab === k ? "border-blue-500 text-blue-400" : "border-transparent text-white/40 hover:text-white/60"}`}>
                      <Icon size={12} /> {label}
                    </button>
                  ))}
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-6">
                  {rightTab === "analyze" ? (
                    /* ─── ANALYZE TAB ────────────────────────────────── */
                    <div className="space-y-4">
                      {/* Job Description Input — Bug 7: field is optional */}
                      <div className="space-y-2">
                        <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wider flex items-center gap-1.5">
                          <FileText size={11} /> Job Description <span className="text-white/30 font-normal normal-case tracking-normal">(optional)</span>
                        </h3>
                        <Textarea
                          value={jobDescription}
                          onChange={(e: any) => setJobDescription(e.target.value)}
                          placeholder="Paste a job description to get a targeted match score, or leave blank for a baseline analysis..."
                          rows={5}
                        />
                        <div className="flex gap-2">
                          <button
                            onClick={runAnalyze}
                            disabled={analyzeLoading}
                            className="flex-1 flex items-center justify-center gap-1.5 py-2 bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/30 rounded-lg text-xs text-blue-400 font-medium transition-colors disabled:opacity-50"
                          >
                            {analyzeLoading ? <Loader2 size={12} className="animate-spin" /> : <BarChart2 size={12} />}
                            {/* Bug 7: button text reflects mode */}
                            {analyzeLoading
                              ? "Analyzing..."
                              : jobDescription.trim()
                                ? "Analyze against job description"
                                : "Run baseline analysis"}
                          </button>
                          <button
                            onClick={runSuggest}
                            disabled={suggestLoading || !resumeId}
                            className="flex-1 flex items-center justify-center gap-1.5 py-2 bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/30 rounded-lg text-xs text-purple-400 font-medium transition-colors disabled:opacity-50"
                          >
                            {suggestLoading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                            {suggestLoading ? "Thinking..." : "Get Tips"}
                          </button>
                        </div>
                      </div>

                      {/* Error */}
                      {analyzeError && (
                        <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                          <AlertCircle size={12} className="text-red-400 shrink-0" />
                          <p className="text-xs text-red-400">{analyzeError}</p>
                          <button onClick={() => setAnalyzeError(null)} className="ml-auto"><X size={10} className="text-red-400" /></button>
                        </div>
                      )}

                      {/* ATS Score Ring */}
                      {atsResult && (() => {
                        const score = atsResult.overall_score ?? atsResult.match_score ?? atsResult.baseline_score ?? 0;
                        const pct = typeof score === "number" ? score : parseFloat(String(score));
                        const color = pct >= 75 ? "#22c55e" : pct >= 50 ? "#f59e0b" : "#ef4444";
                        const r = 36; const circ = 2 * Math.PI * r;
                        const dash = (pct / 100) * circ;
                        return (
                          <div className="space-y-3">
                            <div className="flex items-center gap-4 p-4 bg-white/3 rounded-xl border border-white/5">
                              <svg width="88" height="88" className="shrink-0 -rotate-90">
                                <circle cx="44" cy="44" r={r} fill="none" stroke="#ffffff10" strokeWidth="7" />
                                <circle cx="44" cy="44" r={r} fill="none" stroke={color} strokeWidth="7"
                                  strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
                                  style={{ transition: "stroke-dasharray 0.6s ease" }}
                                />
                              </svg>
                              <div className="rotate-0">
                                <p className="text-2xl font-bold text-white" style={{ color }}>{Math.round(pct)}<span className="text-sm text-white/40">%</span></p>
                                {/* Bug 7: honest label — overall is a blend not a pure match score */}
                                <p className="text-xs text-white/50 mt-0.5">
                                  {atsResult.mode === "targeted"
                                    ? atsResult.match_score == null
                                      ? "Resume strength (JD unreadable)"
                                      : "Overall score (match + strength)"
                                    : "ATS baseline score"}
                                </p>
                                {atsResult.summary && <p className="text-xs text-white/40 mt-1 leading-relaxed">{atsResult.summary.slice(0, 80)}...</p>}
                              </div>
                            </div>

                            {/* Score breakdown */}
                            {atsResult.score_breakdown && (
                              <div className="space-y-1.5">
                                <h4 className="text-xs text-white/40 uppercase tracking-wide">Breakdown</h4>
                                {/* Filter to numeric values only (Bug 6 guard) */}
                                {Object.entries(atsResult.score_breakdown)
                                  .filter(([, v]) => typeof v === "number" && isFinite(v as number))
                                  .map(([k, v]) => (
                                  <div key={k} className="flex items-center gap-2">
                                    <span className="text-xs text-white/50 flex-1 capitalize">{k.replace(/_/g,' ')}</span>
                                    <div className="w-20 h-1.5 bg-white/10 rounded-full overflow-hidden">
                                      <div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.min(100, Number(v))}%`, transition: "width 0.5s ease" }} />
                                    </div>
                                    <span className="text-xs text-white/50 w-6 text-right">{Math.round(Number(v))}</span>
                                  </div>
                                ))}
                              </div>
                            )}

                            {/* Keyword chips */}
                            {((atsResult.missing_keywords?.length ?? 0) > 0 || (atsResult.matched_keywords?.length ?? 0) > 0) && (
                              <div className="space-y-2">
                                <h4 className="text-xs text-white/40 uppercase tracking-wide">Keywords</h4>
                                {atsResult.matched_keywords && atsResult.matched_keywords.length > 0 && (
                                  <div className="flex flex-wrap gap-1">
                                    {atsResult.matched_keywords.slice(0, 12).map(k => (
                                      <span key={k} className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-500/15 text-green-400 border border-green-500/20">{k}</span>
                                    ))}
                                  </div>
                                )}
                                {atsResult.missing_keywords && atsResult.missing_keywords.length > 0 && (
                                  <div>
                                    <p className="text-[10px] text-red-400/60 mb-1">Missing:</p>
                                    <div className="flex flex-wrap gap-1">
                                      {atsResult.missing_keywords.slice(0, 12).map(k => (
                                        <span key={k} className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-500/15 text-red-400 border border-red-500/20">{k}</span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })()}

                      {/* Suggestions cards */}
                      {suggestions.length > 0 && (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider flex items-center gap-1.5"><TrendingUp size={11} /> Suggestions ({suggestions.length})</h4>
                            <button onClick={() => setSuggestions([])} className="text-[10px] text-white/30 hover:text-white/50">Clear</button>
                          </div>
                          {suggestions.slice(0, 8).map((s, i) => (
                            <div key={s.id || i} className="p-3 bg-white/3 border border-white/5 rounded-xl space-y-2">
                              {s.category && <span className="text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded-full">{s.category}</span>}
                              <p className="text-xs text-white/70 leading-relaxed">{s.reason}</p>
                              {s.proposed && (
                                <p className="text-xs text-green-400/80 bg-green-500/5 border border-green-500/10 rounded-lg px-2 py-1.5 leading-relaxed">{s.proposed}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Bullet rewrite modal */}
                      {rewriteResult && (
                        <div className="p-3 bg-purple-900/20 border border-purple-500/30 rounded-xl space-y-2">
                          <div className="flex items-center justify-between">
                            <h4 className="text-xs font-semibold text-purple-300 flex items-center gap-1.5"><Sparkles size={11} /> AI Rewrite</h4>
                            <button onClick={() => setRewriteResult(null)}><X size={12} className="text-white/30" /></button>
                          </div>
                          <p className="text-[10px] text-white/30 line-through leading-relaxed">{rewriteResult.original}</p>
                          <p className="text-xs text-white/80 leading-relaxed">{rewriteResult.suggested}</p>
                          <div className="flex gap-2 mt-2">
                            <button onClick={acceptBulletRewrite} className="flex items-center gap-1 px-3 py-1.5 bg-green-600/20 hover:bg-green-600/30 border border-green-500/30 rounded-lg text-xs text-green-400 transition-colors">
                              <ThumbsUp size={11} /> Accept
                            </button>
                            <button onClick={() => setRewriteResult(null)} className="flex items-center gap-1 px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-xs text-white/50 transition-colors">
                              <ThumbsDown size={11} /> Discard
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Bullet rewrite shortcuts for experience */}
                      {data.experience.length > 0 && (
                        <div className="space-y-2">
                          <h4 className="text-xs text-white/40 uppercase tracking-wide flex items-center gap-1.5"><RefreshCw size={11} /> Rewrite Bullets</h4>
                          {data.experience.slice(0, 3).map((exp, ei) =>
                            exp.bullet_points.slice(0, 3).map((bp, bi) => (
                              <div key={`${ei}-${bi}`} className="flex items-start gap-2 p-2 bg-white/2 rounded-lg border border-white/5">
                                <p className="text-xs text-white/50 flex-1 leading-relaxed truncate">{bp || <span className="text-white/20 italic">empty bullet</span>}</p>
                                <button
                                  disabled={!!rewritingBullet}
                                  onClick={() => runBulletRewrite(bp, "experience", ei, bi)}
                                  className="shrink-0 p-1 bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/20 rounded-lg text-purple-400 transition-colors disabled:opacity-40"
                                  title="AI rewrite"
                                >
                                  {rewritingBullet?.itemIdx === ei && rewritingBullet?.bulletIdx === bi
                                    ? <Loader2 size={11} className="animate-spin" />
                                    : <Sparkles size={11} />}
                                </button>
                              </div>
                            ))
                          )}
                        </div>
                      )}

                      {/* Empty state */}
                      {!atsResult && !analyzeLoading && suggestions.length === 0 && (
                        <div className="text-center py-8 text-white/20">
                          <Sparkles size={32} className="mx-auto mb-3 opacity-30" />
                          <p className="text-xs leading-relaxed">Paste a job description above and click Analyze to get your ATS score and keyword gaps.</p>
                        </div>
                      )}
                    </div>
                  ) : rightTab === "design" ? (
                    <>
                      {/* Template */}
                      <div className="space-y-3">
                        <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wider flex items-center gap-2"><Layers size={12} /> Template</h3>
                        <div className="border border-white/10 rounded-xl overflow-hidden">
                          <div className="bg-white/5 aspect-[3/2] flex items-center justify-center">
                            <FileText size={24} className="text-white/20" />
                          </div>
                          <div className="p-3 space-y-2">
                            <p className="text-sm font-medium text-white">{TEMPLATES.find(t => t.id === templateId)?.name}</p>
                            <button onClick={() => setShowTemplateGallery(true)} className="w-full py-2 border border-white/10 hover:border-white/30 rounded-lg text-xs text-white/50 hover:text-white transition-colors">
                              Change Template
                            </button>
                          </div>
                        </div>
                      </div>

                      {/* Colors */}
                      <div className="space-y-3">
                        <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wider flex items-center gap-2"><Palette size={12} /> Colors</h3>
                        {/* Quick presets */}
                        <div className="flex flex-wrap gap-1.5">
                          {["#2563eb","#7c3aed","#db2777","#dc2626","#ea580c","#16a34a","#0891b2","#4f46e5","#374151","#1a1a1a"].map(c => (
                            <button key={c} onClick={() => setDesign(d => ({ ...d, primary_color: c }))} className={`w-6 h-6 rounded-full border-2 transition-all ${design.primary_color === c ? "border-white scale-110" : "border-transparent hover:scale-105"}`} style={{ backgroundColor: c }} />
                          ))}
                        </div>
                        <FormField label="Primary Color"><ColorInput value={design.primary_color} onChange={v => setDesign(d => ({ ...d, primary_color: v }))} label="Primary" /></FormField>
                        <FormField label="Text Color"><ColorInput value={design.text_color} onChange={v => setDesign(d => ({ ...d, text_color: v }))} label="Text" /></FormField>
                        <FormField label="Background"><ColorInput value={design.background_color} onChange={v => setDesign(d => ({ ...d, background_color: v }))} label="Background" /></FormField>
                      </div>

                      {/* Typography */}
                      <div className="space-y-3">
                        <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wider flex items-center gap-2"><Type size={12} /> Typography</h3>
                        <FormField label="Font Family">
                          <Select value={design.font_family} onChange={v => setDesign(d => ({ ...d, font_family: v }))} options={FONTS} />
                        </FormField>
                        <div className="grid grid-cols-2 gap-3">
                          <FormField label="Font Size"><NumberInput value={design.font_size} onChange={(v: number) => setDesign(d => ({ ...d, font_size: v }))} min={6} max={14} step={0.5} suffix="pt" /></FormField>
                          <FormField label="Line Height"><NumberInput value={design.line_height} onChange={(v: number) => setDesign(d => ({ ...d, line_height: v }))} min={1.0} max={2.0} step={0.05} /></FormField>
                        </div>
                      </div>

                      {/* Page */}
                      <div className="space-y-3">
                        <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wider flex items-center gap-2"><FileText size={12} /> Page</h3>
                        <FormField label="Format">
                          <Select value={design.page_format} onChange={v => setDesign(d => ({ ...d, page_format: v }))} options={["Letter", "A4"]} />
                        </FormField>
                        <div className="grid grid-cols-2 gap-3">
                          <FormField label="Margin X"><NumberInput value={design.margin_x} onChange={(v: number) => setDesign(d => ({ ...d, margin_x: v }))} min={18} max={72} suffix="pt" /></FormField>
                          <FormField label="Margin Y"><NumberInput value={design.margin_y} onChange={(v: number) => setDesign(d => ({ ...d, margin_y: v }))} min={18} max={72} suffix="pt" /></FormField>
                        </div>
                      </div>

                      {/* Export */}
                      <div className="space-y-2">
                        <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wider flex items-center gap-2"><Download size={12} /> Export</h3>
                        <button onClick={handleDownload} className="w-full flex items-center gap-2 py-2.5 px-4 bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/30 rounded-xl text-sm text-blue-400 font-medium transition-colors">
                          <Download size={14} /> Download PDF
                        </button>
                        <button onClick={() => resumeId && window.open(`/tailor?resume_id=${resumeId}`, "_self")} className="w-full flex items-center gap-2 py-2.5 px-4 bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/30 rounded-xl text-sm text-purple-400 font-medium transition-colors">
                          <Zap size={14} /> Open in Tailor
                        </button>
                      </div>
                    </>
                  ) : (
                    /* Layout tab — functional drag-and-drop section reordering */
                    <div className="space-y-4">
                      <div>
                        <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-1">Section Order</h3>
                        <p className="text-xs text-white/30 mb-3">Drag to reorder sections in the preview and PDF.</p>
                        <Reorder.Group
                          axis="y"
                          values={sectionOrder}
                          onReorder={(newOrder) => {
                            setSectionOrder(newOrder);
                            dirtyRef.current = true;
                          }}
                          className="space-y-1"
                        >
                          {sectionOrder.map(key => {
                            // Map schema key → sidebar section key for icon lookup
                            const sidebarKey = key === "custom_sections" ? "custom" : key as SectionKey;
                            const meta = SECTION_META[sidebarKey] || SECTION_META["custom"];
                            const Icon = meta.icon;
                            return (
                              <Reorder.Item
                                key={key}
                                value={key}
                                className="flex items-center gap-2 p-2 rounded-lg bg-white/3 border border-white/5 cursor-grab active:cursor-grabbing hover:border-white/20 transition-colors select-none"
                              >
                                <GripVertical size={12} className="text-white/30" />
                                <Icon size={12} className="text-blue-400/70" />
                                <span className="text-xs text-white/70 flex-1 capitalize">{key.replace(/_/g, ' ')}</span>
                              </Reorder.Item>
                            );
                          })}
                        </Reorder.Group>
                      </div>

                      {/* Section visibility toggles */}
                      <div>
                        <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-2">Section Visibility</h3>
                        <div className="space-y-1">
                          {sectionOrder.map(key => {
                            const sidebarKey = key === "custom_sections" ? "custom" : key as SectionKey;
                            const meta = SECTION_META[sidebarKey] || SECTION_META["custom"];
                            const Icon = meta.icon;
                            // Check if section has any content
                            const hasContent = (() => {
                              if (key === 'summary') return !!data.summary;
                              if (key === 'custom_sections') return data.custom_sections.length > 0;
                              const arr = (data as any)[key];
                              return Array.isArray(arr) && arr.length > 0;
                            })();
                            return (
                              <div key={key} className={`flex items-center gap-2 p-2 rounded-lg border border-white/5 transition-opacity ${hasContent ? '' : 'opacity-40'}`}>
                                <Icon size={12} className="text-white/40" />
                                <span className="text-xs text-white/60 flex-1 capitalize">{key.replace(/_/g, ' ')}</span>
                                {hasContent && (
                                  <span className="text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded-full">✓</span>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </Panel>
            </>
          )}
        </PanelGroup>
      </div>

      {/* Template Gallery Modal */}
      <AnimatePresence>
        {showTemplateGallery && (
          <TemplateGallery
            current={templateId}
            onSelect={setTemplateId}
            onClose={() => setShowTemplateGallery(false)}
          />
        )}
      </AnimatePresence>

      {/* Item Edit Dialogs */}
      <AnimatePresence>
        {editDialog && (
          <EditDialog
            title={`Edit ${editDialog.type.charAt(0).toUpperCase() + editDialog.type.slice(1)}`}
            onClose={() => setEditDialog(null)}
          >
            {editDialog.type === "profiles" && (
              <>
                <FormField label="Network"><Select value={editDialog.data.network} onChange={v => setEditDialog(d => d ? { ...d, data: { ...d.data, network: v } } : null)} options={NETWORKS} /></FormField>
                <FormField label="Username"><Input value={editDialog.data.username} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, username: e.target.value } } : null)} placeholder="johndoe" /></FormField>
                <FormField label="URL"><Input value={editDialog.data.url} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, url: e.target.value } } : null)} placeholder="https://linkedin.com/in/johndoe" /></FormField>
                <button className="w-full py-2 bg-blue-600/20 hover:bg-blue-600/30 rounded-lg text-blue-400 text-sm" onClick={() => { updateItem("profiles", editDialog.index, editDialog.data); setEditDialog(null); }}>Save</button>
              </>
            )}
            {editDialog.type === "experience" && (
              <>
                <FormField label="Company"><Input value={editDialog.data.company} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, company: e.target.value } } : null)} placeholder="Google" /></FormField>
                <FormField label="Position"><Input value={editDialog.data.position} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, position: e.target.value } } : null)} placeholder="Software Engineer" /></FormField>
                <div className="grid grid-cols-2 gap-3">
                  <FormField label="Start Date"><Input value={editDialog.data.start_date} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, start_date: e.target.value } } : null)} placeholder="Jan 2023" /></FormField>
                  <FormField label="End Date"><Input value={editDialog.data.end_date} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, end_date: e.target.value } } : null)} placeholder="Present" /></FormField>
                </div>
                <FormField label="Location"><Input value={editDialog.data.location} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, location: e.target.value } } : null)} placeholder="San Francisco, CA" /></FormField>
                <FormField label="Company URL"><Input value={editDialog.data.url} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, url: e.target.value } } : null)} placeholder="https://google.com" /></FormField>
                <FormField label="Bullet Points (one per line)">
                  <Textarea
                    value={editDialog.data.bullet_points.join("\n")}
                    onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, bullet_points: e.target.value.split("\n") } } : null)}
                    placeholder="• Led a team of 5 engineers..."
                    rows={6}
                  />
                </FormField>
                <button className="w-full py-2 bg-blue-600/20 hover:bg-blue-600/30 rounded-lg text-blue-400 text-sm" onClick={() => { updateItem("experience", editDialog.index, { ...editDialog.data, bullet_points: editDialog.data.bullet_points.filter((b: string) => b.trim()) }); setEditDialog(null); }}>Save</button>
              </>
            )}
            {editDialog.type === "education" && (
              <>
                <FormField label="Institution"><Input value={editDialog.data.institution} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, institution: e.target.value } } : null)} placeholder="MIT" /></FormField>
                <FormField label="Degree"><Input value={editDialog.data.degree} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, degree: e.target.value } } : null)} placeholder="Bachelor of Technology" /></FormField>
                <FormField label="Field"><Input value={editDialog.data.field} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, field: e.target.value } } : null)} placeholder="Computer Science" /></FormField>
                <div className="grid grid-cols-2 gap-3">
                  <FormField label="Grade / GPA"><Input value={editDialog.data.grade} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, grade: e.target.value } } : null)} placeholder="CGPA: 8.5/10" /></FormField>
                  <FormField label="Graduation"><Input value={editDialog.data.graduation_date} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, graduation_date: e.target.value } } : null)} placeholder="May 2024" /></FormField>
                </div>
                <FormField label="Location"><Input value={editDialog.data.location} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, location: e.target.value } } : null)} placeholder="Cambridge, MA" /></FormField>
                <button className="w-full py-2 bg-blue-600/20 hover:bg-blue-600/30 rounded-lg text-blue-400 text-sm" onClick={() => { updateItem("education", editDialog.index, editDialog.data); setEditDialog(null); }}>Save</button>
              </>
            )}
            {editDialog.type === "projects" && (
              <>
                <FormField label="Project Name"><Input value={editDialog.data.name} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, name: e.target.value } } : null)} placeholder="My Awesome Project" /></FormField>
                <FormField label="Period"><Input value={editDialog.data.period} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, period: e.target.value } } : null)} placeholder="Jan 2024" /></FormField>
                <FormField label="Project URL"><Input value={editDialog.data.url} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, url: e.target.value } } : null)} placeholder="https://github.com/user/project" /></FormField>
                <FormField label="Technologies"><TagInput tags={editDialog.data.technologies} onChange={v => setEditDialog(d => d ? { ...d, data: { ...d.data, technologies: v } } : null)} placeholder="Add technology..." /></FormField>
                <FormField label="Bullet Points (one per line)">
                  <Textarea value={editDialog.data.bullets.join("\n")} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, bullets: e.target.value.split("\n") } } : null)} placeholder="• Built with React and FastAPI..." rows={5} />
                </FormField>
                <button className="w-full py-2 bg-blue-600/20 hover:bg-blue-600/30 rounded-lg text-blue-400 text-sm" onClick={() => { updateItem("projects", editDialog.index, { ...editDialog.data, bullets: editDialog.data.bullets.filter((b: string) => b.trim()) }); setEditDialog(null); }}>Save</button>
              </>
            )}
            {editDialog.type === "skills" && (
              <>
                <FormField label="Skill Name"><Input value={editDialog.data.name} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, name: e.target.value } } : null)} placeholder="React" /></FormField>
                <FormField label="Proficiency Level (0 = hidden, 1–5)">
                  <div className="flex items-center gap-3">
                    <input type="range" min={0} max={5} value={editDialog.data.level} onChange={e => setEditDialog(d => d ? { ...d, data: { ...d.data, level: Number(e.target.value) } } : null)} className="flex-1" />
                    <span className="text-sm text-white/60 w-4">{editDialog.data.level}</span>
                  </div>
                </FormField>
                <FormField label="Keywords"><TagInput tags={editDialog.data.keywords} onChange={v => setEditDialog(d => d ? { ...d, data: { ...d.data, keywords: v } } : null)} placeholder="Add keyword..." /></FormField>
                <button className="w-full py-2 bg-blue-600/20 hover:bg-blue-600/30 rounded-lg text-blue-400 text-sm" onClick={() => { updateItem("skills", editDialog.index, editDialog.data); setEditDialog(null); }}>Save</button>
              </>
            )}
            {editDialog.type === "languages" && (
              <>
                <FormField label="Language"><Input value={editDialog.data.language} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, language: e.target.value } } : null)} placeholder="English" /></FormField>
                <FormField label="Fluency"><Select value={editDialog.data.fluency} onChange={v => setEditDialog(d => d ? { ...d, data: { ...d.data, fluency: v } } : null)} options={FLUENCY_LEVELS} /></FormField>
                <button className="w-full py-2 bg-blue-600/20 hover:bg-blue-600/30 rounded-lg text-blue-400 text-sm" onClick={() => { updateItem("languages", editDialog.index, editDialog.data); setEditDialog(null); }}>Save</button>
              </>
            )}
            {editDialog.type === "awards" && (
              <>
                <FormField label="Award Title"><Input value={editDialog.data.title} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, title: e.target.value } } : null)} placeholder="Best Innovation Award" /></FormField>
                <FormField label="Awarded by"><Input value={editDialog.data.awarder} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, awarder: e.target.value } } : null)} placeholder="Company / Organization" /></FormField>
                <FormField label="Date"><Input value={editDialog.data.date} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, date: e.target.value } } : null)} placeholder="2024" /></FormField>
                <FormField label="Description"><Textarea value={editDialog.data.description} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, description: e.target.value } } : null)} placeholder="Brief description..." rows={3} /></FormField>
                <button className="w-full py-2 bg-blue-600/20 hover:bg-blue-600/30 rounded-lg text-blue-400 text-sm" onClick={() => { updateItem("awards", editDialog.index, editDialog.data); setEditDialog(null); }}>Save</button>
              </>
            )}
            {editDialog.type === "certifications" && (
              <>
                <FormField label="Certification Name"><Input value={editDialog.data.title} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, title: e.target.value } } : null)} placeholder="AWS Solutions Architect" /></FormField>
                <FormField label="Issuing Organization"><Input value={editDialog.data.issuer} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, issuer: e.target.value } } : null)} placeholder="Amazon Web Services" /></FormField>
                <div className="grid grid-cols-2 gap-3">
                  <FormField label="Date"><Input value={editDialog.data.date} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, date: e.target.value } } : null)} placeholder="Dec 2023" /></FormField>
                  <FormField label="Credential URL"><Input value={editDialog.data.url} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, url: e.target.value } } : null)} placeholder="https://..." /></FormField>
                </div>
                <button className="w-full py-2 bg-blue-600/20 hover:bg-blue-600/30 rounded-lg text-blue-400 text-sm" onClick={() => { updateItem("certifications", editDialog.index, editDialog.data); setEditDialog(null); }}>Save</button>
              </>
            )}
            {editDialog.type === "publications" && (
              <>
                <FormField label="Title"><Input value={editDialog.data.title} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, title: e.target.value } } : null)} placeholder="Paper title..." /></FormField>
                <FormField label="Publisher"><Input value={editDialog.data.publisher} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, publisher: e.target.value } } : null)} placeholder="IEEE / ACM / Nature..." /></FormField>
                <div className="grid grid-cols-2 gap-3">
                  <FormField label="Date"><Input value={editDialog.data.date} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, date: e.target.value } } : null)} placeholder="2024" /></FormField>
                  <FormField label="URL"><Input value={editDialog.data.url} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, url: e.target.value } } : null)} placeholder="https://doi.org/..." /></FormField>
                </div>
                <FormField label="Summary"><Textarea value={editDialog.data.summary} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, summary: e.target.value } } : null)} rows={3} /></FormField>
                <button className="w-full py-2 bg-blue-600/20 hover:bg-blue-600/30 rounded-lg text-blue-400 text-sm" onClick={() => { updateItem("publications", editDialog.index, editDialog.data); setEditDialog(null); }}>Save</button>
              </>
            )}
            {editDialog.type === "volunteer" && (
              <>
                <FormField label="Organization"><Input value={editDialog.data.organization} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, organization: e.target.value } } : null)} placeholder="Red Cross" /></FormField>
                <FormField label="Position"><Input value={editDialog.data.position} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, position: e.target.value } } : null)} placeholder="Volunteer Coordinator" /></FormField>
                <div className="grid grid-cols-2 gap-3">
                  <FormField label="Location"><Input value={editDialog.data.location} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, location: e.target.value } } : null)} /></FormField>
                  <FormField label="Period"><Input value={editDialog.data.period} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, period: e.target.value } } : null)} placeholder="2022 – Present" /></FormField>
                </div>
                <FormField label="Description"><Textarea value={editDialog.data.description} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, description: e.target.value } } : null)} rows={3} /></FormField>
                <button className="w-full py-2 bg-blue-600/20 hover:bg-blue-600/30 rounded-lg text-blue-400 text-sm" onClick={() => { updateItem("volunteer", editDialog.index, editDialog.data); setEditDialog(null); }}>Save</button>
              </>
            )}
            {editDialog.type === "interests" && (
              <>
                <FormField label="Interest"><Input value={editDialog.data.name} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, name: e.target.value } } : null)} placeholder="Open Source" /></FormField>
                <FormField label="Keywords"><TagInput tags={editDialog.data.keywords} onChange={v => setEditDialog(d => d ? { ...d, data: { ...d.data, keywords: v } } : null)} placeholder="Add keyword..." /></FormField>
                <button className="w-full py-2 bg-blue-600/20 hover:bg-blue-600/30 rounded-lg text-blue-400 text-sm" onClick={() => { updateItem("interests", editDialog.index, editDialog.data); setEditDialog(null); }}>Save</button>
              </>
            )}
            {editDialog.type === "references" && (
              <>
                <FormField label="Name"><Input value={editDialog.data.name} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, name: e.target.value } } : null)} placeholder="John Smith" /></FormField>
                <FormField label="Position / Company"><Input value={editDialog.data.position} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, position: e.target.value } } : null)} placeholder="CTO at Acme Corp" /></FormField>
                <FormField label="Phone"><Input value={editDialog.data.phone} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, phone: e.target.value } } : null)} /></FormField>
                <FormField label="Email / URL"><Input value={editDialog.data.url} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, url: e.target.value } } : null)} /></FormField>
                <button className="w-full py-2 bg-blue-600/20 hover:bg-blue-600/30 rounded-lg text-blue-400 text-sm" onClick={() => { updateItem("references", editDialog.index, editDialog.data); setEditDialog(null); }}>Save</button>
              </>
            )}
            {editDialog.type === "custom_item" && (
              <>
                <FormField label="Title"><Input value={editDialog.data.item.title} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, item: { ...d.data.item, title: e.target.value } } } : null)} /></FormField>
                <FormField label="Subtitle"><Input value={editDialog.data.item.subtitle} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, item: { ...d.data.item, subtitle: e.target.value } } } : null)} /></FormField>
                <FormField label="Date"><Input value={editDialog.data.item.date} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, item: { ...d.data.item, date: e.target.value } } } : null)} /></FormField>
                <FormField label="Bullets (one per line)">
                  <Textarea value={editDialog.data.item.bullets.join("\n")} onChange={(e: any) => setEditDialog(d => d ? { ...d, data: { ...d.data, item: { ...d.data.item, bullets: e.target.value.split("\n") } } } : null)} rows={4} />
                </FormField>
                <button className="w-full py-2 bg-blue-600/20 hover:bg-blue-600/30 rounded-lg text-blue-400 text-sm" onClick={() => {
                  const { sectionIndex, item } = editDialog.data;
                  updateData(d => { const arr = [...d.custom_sections]; arr[sectionIndex].items[editDialog.index] = { ...arr[sectionIndex].items[editDialog.index], ...item, bullets: item.bullets.filter((b: string) => b.trim()) }; return { ...d, custom_sections: arr }; });
                  setEditDialog(null);
                }}>Save</button>
              </>
            )}
          </EditDialog>
        )}
      </AnimatePresence>
    </div>
  );
}
