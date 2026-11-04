"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import {
  Panel,
  Section,
  Divider,
  Button,
  Tag,
  Textarea,
  Spinner,
  Score,
  ScoreBar,
  Stat,
  StatRow,
  Table,
  Th,
  Td,
  Tr,
  Toolbar,
  Segmented,
  Note,
  EmptyState,
} from "../components/ui";
import {
  getResumes, analyzeATS, updateSuggestion, improvePropose, improveApply, uploadResume,
  ResumeVersion, ATSResult, SuggestionItem, ImproveApplyResult, ImproveProposeResult, ChangeItem, improveBullet, ImproveBulletResult,
  extractResumeText, analyzeATSText
} from "../lib/api";
import { X, Send } from "lucide-react";

// ─── Formatting Health ───────────────────────────────────────────────────────
const FORMATTING_LABELS: Record<string, string> = {
  single_column: "Single-column layout",
  no_tables: "No tables detected",
  text_based_pdf: "Text-based PDF (not scanned)",
  no_ligatures: "No ligature characters",
  standard_length: "Optimal length (300–800 words)",
  single_page: "Fits on one page",
  consistent_dates: "Consistent date formatting",
  consistent_bullets: "Consistent bullet style",
  no_excessive_whitespace: "No excessive blank space",
  experience_before_education: "Experience listed before Education",
};

function FormattingHealthCard({ health }: { health: Record<string, boolean> }) {
  const passCount = Object.values(health).filter(Boolean).length;
  const total = Object.keys(health).length;
  return (
    <Section
      title="Formatting"
      action={
        <span
          data-numeric
          className={
            passCount === total
              ? "text-sm text-good"
              : passCount >= total * 0.7
              ? "text-sm text-warn"
              : "text-sm text-bad"
          }
        >
          {passCount}/{total} passed
        </span>
      }
    >
      <ul className="grid gap-x-8 sm:grid-cols-2">
        {Object.entries(health).map(([key, passed]) => (
          <li
            key={key}
            className="flex items-baseline justify-between gap-3 border-b border-rule py-2 text-sm"
          >
            <span className="text-ink-secondary">
              {FORMATTING_LABELS[key] ?? key}
            </span>
            <span className={passed ? "text-good" : "text-bad"}>
              {passed ? "Pass" : "Fail"}
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

// ─── Line-by-Line Bullet Annotations ─────────────────────────────────────────
const QUALITY_LABEL: Record<string, string> = {
  excellent: "Excellent",
  good: "Good",
  acceptable: "Acceptable",
  needs_work: "Needs work",
};

/** Quality maps to a left rule, not a background tint. */
const QUALITY_RULE: Record<string, string> = {
  excellent: "border-l-good",
  good: "border-l-good",
  acceptable: "border-l-warn",
  needs_work: "border-l-bad",
};

const QUALITY_TEXT: Record<string, string> = {
  excellent: "text-good",
  good: "text-good",
  acceptable: "text-warn",
  needs_work: "text-bad",
};

function LineByLineBulletAnnotationsCard({ annotations }: { annotations: any }) {
  const stats = annotations?.summary_stats || {};
  const sections = [
    { key: "experience", title: "Work experience" },
    { key: "projects", title: "Projects" },
  ];

  return (
    <Section
      title="Bullet feedback"
      action={
        <span className="text-sm text-ink-tertiary">
          <span className="text-good">{stats.excellent || 0} excellent</span>
          {" · "}
          <span>{stats.good || 0} good</span>
          {" · "}
          <span className="text-bad">{stats.needs_work || 0} need work</span>
        </span>
      }
    >
      <div className="space-y-8">
        {sections.map((sec) => {
          const items = annotations[sec.key] || [];
          if (items.length === 0) return null;
          return (
            <div key={sec.key} className="space-y-5">
              <p className="text-xs uppercase tracking-wide text-ink-tertiary">
                {sec.title}
              </p>
              {items.map((item: any, idx: number) => (
                <div key={idx} className="space-y-3">
                  <p className="text-sm font-medium text-ink">
                    {item.title} {item.company ? `— ${item.company}` : ""}
                  </p>
                  {item.bullet_annotations?.map((bAnn: any, bIdx: number) => (
                    <div
                      key={bIdx}
                      className={`border-l-2 pl-3.5 ${
                        QUALITY_RULE[bAnn.quality] ?? "border-l-rule-strong"
                      }`}
                    >
                      <div className="flex items-baseline justify-between gap-4">
                        <p className="flex-1 text-sm leading-relaxed text-ink-secondary">
                          {bAnn.bullet}
                        </p>
                        <span
                          className={`shrink-0 text-xs ${
                            QUALITY_TEXT[bAnn.quality] ?? "text-ink-tertiary"
                          }`}
                        >
                          {QUALITY_LABEL[bAnn.quality] ?? bAnn.quality}
                        </span>
                      </div>
                      {bAnn.annotations && bAnn.annotations.length > 0 && (
                        <p className="mt-1.5 text-xs text-ink-tertiary">
                          {bAnn.annotations
                            .map((ann: any) => ann.text)
                            .join(" · ")}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </Section>
  );
}

import { useTasks } from "../context/TaskContext";

export default function ATSPage() {
  const {
    atsResult: result,
    setAtsResult: setResult,
    atsError,
    setAtsError,
    jobDescription,
    setJobDescription,
  } = useTasks();

  const [activeTab, setActiveTab] = useState<"upload" | "paste">("upload");
  const [uploadedFile, setUploadedFile] = useState<{ name: string; size: string; url: string } | null>(null);
  const [resumeText, setResumeText] = useState("");
  const [activeResumeId, setActiveResumeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [improving, setImproving] = useState(false);
  const [analyzingLocal, setAnalyzingLocal] = useState(false);
  const [analyzeStep, setAnalyzeStep] = useState(0);
  const [improvedResult, setImprovedResult] = useState<ImproveApplyResult | null>(null);
  const [proposedChanges, setProposedChanges] = useState<ChangeItem[]>([]);
  const [acceptedChanges, setAcceptedChanges] = useState<ChangeItem[]>([]);
  const [rejectedIndexes, setRejectedIndexes] = useState<number[]>([]);
  const [applying, setApplying] = useState(false);
  const [rewritingBullet, setRewritingBullet] = useState<number | null>(null);
  const [bulletRewrites, setBulletRewrites] = useState<Record<number, ImproveBulletResult>>({});
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Improve Drawer state ──
  const [showImproveDrawer, setShowImproveDrawer] = useState(false);
  const [chatMessages, setChatMessages] = useState<{ role: "user" | "ai"; text: string }[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [showDiffViewer, setShowDiffViewer] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Sync global error
  useEffect(() => {
    if (atsError) setError(atsError);
  }, [atsError]);

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };

  const handleFileUpload = useCallback(async (file: File) => {
    if (!file) return;
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext !== "pdf" && ext !== "docx" && ext !== "png" && ext !== "jpg" && ext !== "jpeg") {
      setError("Only PDF, DOCX, and images (PNG, JPG) are supported.");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      // Upload the file to database AND disk. This creates a ResumeVersion and saves raw file bytes.
      const res = await uploadResume(file, "ats_check");
      const rawText = res.parsed_data?._raw || "";
      setResumeText(rawText);
      if (res.resume_id) {
        setActiveResumeId(res.resume_id);
      }
      setUploadedFile({
        name: file.name,
        size: formatFileSize(file.size),
        url: URL.createObjectURL(file),
      });
    } catch (err: any) {
      setError(err.message || "File upload failed.");
    } finally {
      setUploading(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileUpload(file);
  }, [handleFileUpload]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  const ANALYZE_STEPS = [
    "Extracting resume structure…",
    "Parsing skills and experience…",
    "Running ATS compatibility checks…",
    "Calculating score…",
    "Finalizing results…",
  ];

  async function handleAnalyze() {
    const textToAnalyze = resumeText;
    if (!textToAnalyze.trim()) {
      setError(
        activeTab === "upload"
          ? "Please upload a resume file first."
          : "Please paste your resume text first."
      );
      return;
    }
    setAnalyzingLocal(true);
    setAnalyzeStep(0);
    setError(null);
    setImprovedResult(null);

    // Cycle through step messages while waiting
    const stepInterval = setInterval(() => {
      setAnalyzeStep((s) => Math.min(s + 1, ANALYZE_STEPS.length - 1));
    }, 4000);

    try {
      let data;
      if (activeTab === "upload" && activeResumeId) {
        // Run ATS analysis on the uploaded resume ID.
        // This preserves the exact original document that the user uploaded!
        data = await analyzeATS(activeResumeId, jobDescription);
      } else {
        // Text pasted mode
        data = await analyzeATSText(textToAnalyze, jobDescription);
      }
      setResult(data);
      if (data.resume_id) {
        setActiveResumeId(data.resume_id);
      }
    } catch (err: any) {
      setError(err.message || "Analysis failed.");
    } finally {
      clearInterval(stepInterval);
      setAnalyzingLocal(false);
      setAnalyzeStep(0);
    }
  }

  async function handleImprove(userInstructions?: string) {
    if (!activeResumeId) return;
    setImproving(true);
    setError(null);
    setProposedChanges([]);
    setRejectedIndexes([]);
    setShowDiffViewer(false);

    const mode = userInstructions ? "custom" : "auto_improve";

    if (userInstructions) {
      setChatMessages((prev) => [...prev, { role: "user", text: userInstructions }]);
    }

    try {
      const data = await improvePropose(
        activeResumeId,
        mode,
        undefined,
        jobDescription || undefined
      );
      setProposedChanges(data.proposed_changes);
      // Stay in chat view — user clicks the inline 'Review & Apply' button in the status bubble
      const count = data.proposed_changes.length;
      const aiMsg = count > 0
        ? `I analyzed your resume and found ${count} safe improvements to make. Review them below!`
        : `I analyzed your resume and everything looks great! No improvements needed right now.`;
      setChatMessages((prev) => [...prev, { role: "ai", text: aiMsg }]);
    } catch (err: any) {
      setError(err.message || "Improvement proposal failed.");
      setChatMessages((prev) => [...prev, { role: "ai", text: "I encountered an error trying to improve your resume. Please try again." }]);
    } finally {
      setImproving(false);
    }
  }

  async function handleApplyChanges() {
    if (!activeResumeId) return;
    setApplying(true);
    setError(null);
    try {
      const changesToApply = proposedChanges.filter((_, i) => !rejectedIndexes.includes(i));
      const data = await improveApply(activeResumeId, changesToApply);

      setImprovedResult(data as any);
      if ((data as any).new_ats_result) {
        setResult((data as any).new_ats_result);
      }
      if (data.improved_resume_id) {
        setActiveResumeId(data.improved_resume_id);
      }
      setProposedChanges([]);
    } catch (err: any) {
       setError(err.message || "Failed to apply changes.");
    } finally {
       setApplying(false);
    }
  }

  function openImproveDrawer() {
    setShowImproveDrawer(true);
    setShowDiffViewer(false);
    setImprovedResult(null);
    setProposedChanges([]);
    setRejectedIndexes([]);
    // Always start fresh — reset chat so no stale analysis messages pile up
    setChatMessages([{
      role: "ai",
      text: "I can help improve your resume. Use Auto-improve for safe, conservative changes (readability, metrics, action verbs) — no structural changes. Or type specific instructions below, e.g. \"Add a professional summary\" or \"Rewrite my project bullets to highlight React\"."
    }]);
  }

  function handleChatSend() {
    if (!chatInput.trim() || improving) return;
    const msg = chatInput.trim();
    setChatInput("");
    handleImprove(msg);
  }

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  async function handleSuggestionAction(
    suggestionId: string,
    action: "accepted" | "rejected"
  ) {
    try {
      await updateSuggestion(suggestionId, action);
      // Update local state
      if (result) {
        setResult({
          ...result,
          suggestions_created: result.suggestions_created.map((s) =>
            s.id === suggestionId ? { ...s, status: action } : s
          ),
        });
      }
    } catch (err: any) {
      setError(err.message || "Failed to update suggestion.");
    }
  }

  async function handleRewriteBullet(index: number, text: string) {
    setRewritingBullet(index);
    try {
      const res = await improveBullet(text, jobDescription || undefined);
      setBulletRewrites((prev) => ({ ...prev, [index]: res }));
    } catch (err: any) {
      alert("Failed to rewrite bullet: " + err.message);
    } finally {
      setRewritingBullet(null);
    }
  }

  // Bug 6: overall_score is the headline blend (always present);
  // match_score and baseline_score are separate distinct numbers.
  const score = result?.overall_score ?? result?.baseline_score ?? null;

  // Score band — five words, three inks. Colour supports the word, never replaces it.
  function getScoreBand(s: number): { label: string; text: string; verdict: string } {
    if (s >= 85)
      return {
        label: "Excellent",
        text: "text-good",
        verdict:
          "Well-structured, keyword-rich, and ready for most ATS systems.",
      };
    if (s >= 70)
      return {
        label: "Good",
        text: "text-good",
        verdict:
          "Good ATS compatibility. A few improvements push this to the top tier.",
      };
    if (s >= 55)
      return {
        label: "Average",
        text: "text-warn",
        verdict:
          "Room for improvement. Address the high-priority issues below to stand out.",
      };
    if (s >= 40)
      return {
        label: "Needs work",
        text: "text-warn",
        verdict:
          "Several critical areas are missing. Fix high-priority issues first.",
      };
    return {
      label: "Critical",
      text: "text-bad",
      verdict: "This resume will likely be filtered out by ATS systems.",
    };
  }

  /** Severity reads as a word against a left rule. */
  const SEVERITY_RULE: Record<string, string> = {
    high: "border-l-bad",
    medium: "border-l-warn",
    low: "border-l-rule-strong",
  };
  const SEVERITY_TEXT: Record<string, string> = {
    high: "text-bad",
    medium: "text-warn",
    low: "text-ink-tertiary",
  };
  const SEVERITY_LABEL: Record<string, string> = {
    high: "High",
    medium: "Medium",
    low: "Low",
  };

  const fileExtension = uploadedFile?.name.split(".").pop()?.toUpperCase() || "PDF";

  return (
    <div className="space-y-12 pb-20">
      <header>
        <h1 className="text-3xl">ATS</h1>
        <p className="mt-1.5 text-sm text-ink-tertiary">
          Score a resume against a job description and get specific fixes.
        </p>
      </header>

      {/* ── Input ─────────────────────────────────────────────────────── */}
      <Section
        title="Analyse"
        action={
          <Segmented
            value={activeTab}
            onChange={(v) => {
              setActiveTab(v);
              setError(null);
            }}
            options={[
              { value: "upload", label: "Upload" },
              { value: "paste", label: "Paste text" },
            ]}
          />
        }
      >
        <div className="space-y-6">
          {activeTab === "upload" && (
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
            >
              {!uploadedFile && !uploading ? (
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className={`flex w-full flex-col items-center justify-center border border-dashed px-6 py-12 text-center transition-colors duration-100 ${
                    dragOver
                      ? "border-accent bg-accent/[0.04]"
                      : "border-rule-strong hover:border-ink-tertiary hover:bg-sunken"
                  }`}
                >
                  <p className="font-serif text-lg text-ink">
                    Drop a resume, or click to browse
                  </p>
                  <p className="mt-1.5 text-sm text-ink-tertiary">
                    PDF, DOCX, PNG or JPG — up to 10 MB
                  </p>
                </button>
              ) : uploading ? (
                <div className="flex flex-col items-center justify-center border border-dashed border-rule-strong px-6 py-12">
                  <Spinner />
                  <p className="mt-3 text-sm text-ink-tertiary">
                    Parsing file and extracting text…
                  </p>
                </div>
              ) : (
                <Panel className="flex items-center gap-4 p-4">
                  <span className="shrink-0 rounded border border-rule px-2 py-1 text-xs uppercase tracking-wide text-ink-tertiary">
                    {fileExtension}
                  </span>
                  <div className="min-w-0 flex-1">
                    <a
                      href={uploadedFile.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block truncate text-sm text-ink hover:text-accent"
                    >
                      {uploadedFile.name}
                    </a>
                    <p className="text-xs text-ink-tertiary">
                      {uploadedFile.size} · ready to analyse
                    </p>
                  </div>
                  <Toolbar className="shrink-0">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      Change
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        if (uploadedFile.url) {
                          URL.revokeObjectURL(uploadedFile.url);
                        }
                        setUploadedFile(null);
                        setResumeText("");
                      }}
                    >
                      Remove
                    </Button>
                  </Toolbar>
                </Panel>
              )}

              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.png,.jpg,.jpeg"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFileUpload(file);
                  e.target.value = "";
                }}
              />
            </div>
          )}

          {activeTab === "paste" && (
            <div className="space-y-1.5">
              <label className="block text-xs uppercase tracking-wide text-ink-tertiary">
                Resume text
              </label>
              <Textarea
                placeholder="Paste the full text of your resume here…"
                value={resumeText}
                onChange={(e) => setResumeText(e.target.value)}
                className="min-h-[220px]"
              />
            </div>
          )}

          <div className="space-y-1.5">
            <label className="block text-xs uppercase tracking-wide text-ink-tertiary">
              Job description{" "}
              <span className="normal-case tracking-normal">
                — optional, leave empty for a baseline analysis
              </span>
            </label>
            <Textarea
              placeholder="Paste the full job description here…"
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              className="min-h-[160px]"
            />
          </div>

          <Toolbar>
            <Button
              onClick={handleAnalyze}
              disabled={analyzingLocal || !resumeText.trim()}
            >
              {analyzingLocal ? (
                <>
                  <Spinner className="mr-1.5" />
                  {ANALYZE_STEPS[analyzeStep]}
                </>
              ) : jobDescription.trim() ? (
                "Analyse against job description"
              ) : (
                "Run baseline analysis"
              )}
            </Button>
          </Toolbar>

          {error && <Note variant="bad">{error}</Note>}
        </div>
      </Section>

      {/* ── Results ───────────────────────────────────────────────────── */}
      {result && (
        <div className="space-y-12">
          {score !== null && (() => {
            const band = getScoreBand(score);
            const issues = result.issues ?? [];
            const highIssues = issues.filter((i) => i.severity === "high");
            const medIssues = issues.filter((i) => i.severity === "medium");
            const lowIssues = issues.filter((i) => i.severity === "low");
            const isTargeted = result.mode === "targeted";
            const matchUnavailable = isTargeted && result.match_score == null;
            return (
              <>
                {/* Score header — a numeral, a word, a verdict. */}
                <section className="space-y-6">
                  {/* Bug 6: jd_extraction_status caveat */}
                  {isTargeted && (result.jd_extraction_status === "failed" || result.jd_extraction_status === "low_confidence") && (
                    <Note variant="bad">
                      {result.jd_extraction_status === "failed"
                        ? (result.match_fallback_reason ?? "Job description could not be read — no recognised skills found. Showing resume strength score only.")
                        : "Job description was partially read (low confidence). Match score may be incomplete."}
                    </Note>
                  )}

                  <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                    <span
                      data-numeric
                      className={`font-serif text-[64px] leading-none ${band.text}`}
                    >
                      {score}
                    </span>
                    <span className="text-xl text-ink-tertiary">/100</span>
                    <span className={`text-xl ${band.text}`}>{band.label}</span>
                    {/* Bug 6: honest label — overall_score is a blend, not a pure match score */}
                    <span className="w-full text-xs uppercase tracking-wide text-ink-tertiary">
                      {isTargeted
                        ? matchUnavailable
                          ? "Resume strength score (JD unreadable)"
                          : "Overall score (match + strength blend)"
                        : "ATS friendliness score"}
                    </span>
                  </div>

                  <ScoreBar score={score} />

                  {/* Bug 6: In targeted mode show both distinct scores */}
                  {isTargeted && !matchUnavailable && (
                    <div className="flex flex-wrap gap-6 text-sm">
                      <span className="text-ink-secondary">
                        Resume strength: <span data-numeric className="text-ink font-medium">{result.baseline_score ?? "—"}</span><span className="text-ink-tertiary">/100</span>
                      </span>
                      <span className="text-ink-secondary">
                        JD match: <span data-numeric className="text-ink font-medium">{result.match_score ?? "—"}</span><span className="text-ink-tertiary">/100</span>
                      </span>
                    </div>
                  )}

                  {/* Bug 6: match_score null — show baseline note instead of zero */}
                  {matchUnavailable && result.baseline_score != null && (
                    <div className="text-sm text-ink-secondary">
                      Resume strength: <span data-numeric className="text-ink font-medium">{result.baseline_score}</span><span className="text-ink-tertiary">/100</span>
                    </div>
                  )}

                  <p className="max-w-2xl text-base text-ink-secondary">
                    {band.verdict}
                  </p>

                  {result.summary && (
                    <Note>{result.summary}</Note>
                  )}

                  <Toolbar>
                    <Button variant="secondary" onClick={openImproveDrawer}>
                      Improve resume
                    </Button>
                    {improvedResult && (
                      <>
                        <span className="text-sm text-good">Applied</span>
                        <button
                          type="button"
                          onClick={() => {
                            setShowImproveDrawer(true);
                            setShowDiffViewer(true);
                          }}
                          className="text-sm text-accent hover:underline"
                        >
                          View changes
                        </button>
                      </>
                    )}
                  </Toolbar>
                </section>

                {/* Issues — left rule + severity word. */}
                {issues.length > 0 && (
                  <Section
                    title="Issues"
                    description="Fix these to improve the score."
                    action={
                      <span data-numeric className="text-sm text-ink-tertiary">
                        {issues.length}
                      </span>
                    }
                  >
                    <ul className="space-y-4">
                      {[...highIssues, ...medIssues, ...lowIssues].map(
                        (issue, idx) => (
                          <li
                            key={idx}
                            className={`border-l-2 pl-3.5 ${
                              SEVERITY_RULE[issue.severity] ??
                              "border-l-rule-strong"
                            }`}
                          >
                            <div className="flex items-baseline justify-between gap-4">
                              <p className="text-sm font-medium text-ink">
                                {issue.issue}
                              </p>
                              <span
                                className={`shrink-0 text-xs ${
                                  SEVERITY_TEXT[issue.severity] ??
                                  "text-ink-tertiary"
                                }`}
                              >
                                {SEVERITY_LABEL[issue.severity] ??
                                  issue.severity}
                                {issue.points_deducted > 0 && (
                                  <span data-numeric>
                                    {" "}
                                    · −{issue.points_deducted}
                                  </span>
                                )}
                              </span>
                            </div>
                            <p className="mt-1 text-sm text-ink-secondary">
                              {issue.suggestion}
                            </p>
                          </li>
                        )
                      )}
                    </ul>
                  </Section>
                )}

                {result.formatting_health && (
                  <FormattingHealthCard health={result.formatting_health} />
                )}

                {result.bullet_annotations && (
                  <LineByLineBulletAnnotationsCard
                    annotations={result.bullet_annotations}
                  />
                )}
              </>
            );
          })()}

          {/* Bullet Point Enhancer */}
          {result.bullet_point_analysis && result.bullet_point_analysis.length > 0 && (
            <Section
              title="Bullet enhancer"
              description="Rewrite individual weak bullets."
            >
              <div className="space-y-6">
                {result.bullet_point_analysis.map((item: any, idx: number) => (
                  <div key={idx} className="border-b border-rule pb-5 last:border-0">
                    <p className="text-sm text-ink">{item.bullet}</p>
                    <div className="mt-2.5 flex flex-wrap items-center justify-between gap-3">
                      <Toolbar>
                        <Tag variant={item.has_action_verb ? "good" : "bad"}>
                          {item.has_action_verb ? "Action verb" : "No action verb"}
                        </Tag>
                        <Tag variant={item.has_metrics ? "good" : "default"}>
                          {item.has_metrics ? "Metrics" : "No metrics"}
                        </Tag>
                      </Toolbar>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleRewriteBullet(idx, item.bullet)}
                        disabled={rewritingBullet === idx}
                      >
                        {rewritingBullet === idx ? (
                          <>
                            <Spinner className="mr-1.5" />
                            Rewriting…
                          </>
                        ) : (
                          "Rewrite"
                        )}
                      </Button>
                    </div>

                    {bulletRewrites[idx] && (
                      <div className="mt-4 space-y-2 border-l-2 border-l-good pl-3.5">
                        <p className="text-xs uppercase tracking-wide text-ink-tertiary">
                          Suggested
                        </p>
                        <p className="text-sm text-ink">
                          {bulletRewrites[idx].suggested}
                        </p>
                        <p className="text-sm text-ink-tertiary">
                          {bulletRewrites[idx].reasoning}
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Score Breakdown */}
          {result.score_breakdown && Object.keys(result.score_breakdown).length > 0 && (
            <Section
              title="Breakdown"
              description="How the resume scored in each category."
            >
              <div className="space-y-4">
                {/* Bug 6: filter to numeric values only — match/role_fit are null in baseline mode */}
                {Object.entries(result.score_breakdown)
                  .filter(([, value]) => typeof value === "number" && isFinite(value))
                  .map(([key, value]) => {
                    const label = key
                      .replace(/_/g, " ")
                      .replace(/\b\w/g, (c) => c.toUpperCase());
                    return (
                      <div key={key} className="space-y-1.5">
                        <div className="flex items-baseline justify-between text-sm">
                          <span className="text-ink-secondary">{label}</span>
                          <span data-numeric className="text-ink">
                            {value}
                            <span className="text-ink-tertiary">/100</span>
                          </span>
                        </div>
                        <ScoreBar score={value} />
                      </div>
                    );
                  })}
              </div>
            </Section>
          )}

          {/* Keywords */}
          {(result.matched_keywords?.length || result.missing_keywords?.length) && (
            <div className="grid gap-10 md:grid-cols-2">
              {result.matched_keywords && result.matched_keywords.length > 0 && (
                <Section
                  title="Matched keywords"
                  action={
                    <span data-numeric className="text-sm text-ink-tertiary">
                      {result.matched_keywords.length}
                    </span>
                  }
                >
                  <div className="flex flex-wrap gap-1.5">
                    {result.matched_keywords.map((kw, i) => (
                      <Tag key={i} variant="good">
                        {kw}
                      </Tag>
                    ))}
                  </div>
                </Section>
              )}

              {result.missing_keywords && result.missing_keywords.length > 0 && (
                <Section
                  title="Missing keywords"
                  action={
                    <span data-numeric className="text-sm text-ink-tertiary">
                      {result.missing_keywords.length}
                    </span>
                  }
                >
                  <div className="flex flex-wrap gap-1.5">
                    {result.missing_keywords.map((kw, i) => (
                      <Tag key={i} variant="bad">
                        {kw}
                      </Tag>
                    ))}
                  </div>
                </Section>
              )}
            </div>
          )}

          {/* Suggestions — a table with inline accept / reject. */}
          {result.suggestions_created && result.suggestions_created.length > 0 && (
            <Section
              title="Suggestions"
              description="Accept to apply, reject to dismiss."
            >
              <Table>
                <thead>
                  <tr>
                    <Th>Suggestion</Th>
                    <Th className="w-[120px]">Category</Th>
                    <Th className="w-[160px] text-right">Action</Th>
                  </tr>
                </thead>
                <tbody>
                  {result.suggestions_created.map((suggestion) => (
                    <Tr key={suggestion.id}>
                      <Td className="align-top">
                        <p className="font-medium text-ink">
                          {suggestion.reason}
                        </p>
                        {suggestion.original && (
                          <p className="mt-1.5 text-sm">
                            <span className="text-ink-tertiary">From: </span>
                            <span className="diff-del">
                              {suggestion.original}
                            </span>
                          </p>
                        )}
                        {suggestion.suggested && (
                          <p className="mt-1 text-sm">
                            <span className="text-ink-tertiary">To: </span>
                            <span className="diff-add">
                              {suggestion.suggested}
                            </span>
                          </p>
                        )}
                        {suggestion.suggestion && !suggestion.suggested && (
                          <p className="mt-1.5 text-sm text-ink-secondary">
                            {suggestion.suggestion}
                          </p>
                        )}
                      </Td>
                      <Td className="align-top">
                        {suggestion.category && (
                          <span className="text-ink-tertiary">
                            {suggestion.category}
                          </span>
                        )}
                        {suggestion.severity && (
                          <span
                            className={`block text-xs ${
                              SEVERITY_TEXT[suggestion.severity] ??
                              "text-ink-tertiary"
                            }`}
                          >
                            {SEVERITY_LABEL[suggestion.severity] ??
                              suggestion.severity}
                          </span>
                        )}
                      </Td>
                      <Td className="align-top text-right">
                        {suggestion.status === "pending" ? (
                          <div className="flex justify-end gap-2">
                            <button
                              type="button"
                              onClick={() =>
                                handleSuggestionAction(suggestion.id, "accepted")
                              }
                              className="text-sm text-good hover:underline"
                            >
                              Accept
                            </button>
                            <span className="text-rule-strong">·</span>
                            <button
                              type="button"
                              onClick={() =>
                                handleSuggestionAction(suggestion.id, "rejected")
                              }
                              className="text-sm text-ink-tertiary hover:text-bad hover:underline"
                            >
                              Reject
                            </button>
                          </div>
                        ) : (
                          <span
                            className={
                              suggestion.status === "accepted"
                                ? "text-sm text-good"
                                : "text-sm text-ink-tertiary"
                            }
                          >
                            {suggestion.status === "accepted"
                              ? "Accepted"
                              : "Rejected"}
                          </span>
                        )}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            </Section>
          )}

          {/* Raw report — folded away, for when you need it. */}
          {/* Bug 5: raw report uses real fields only — dead fields removed */}
          {(result.overall_score != null || result.baseline_score != null) && (
            <details className="group">
              <summary className="cursor-pointer border-b border-rule pb-2 text-sm text-ink-tertiary hover:text-ink">
                Full report (raw)
              </summary>
              <pre className="mt-4 overflow-x-auto bg-sunken p-4 font-mono text-xs leading-relaxed text-ink-secondary">
                {JSON.stringify({
                  mode: result.mode,
                  overall_score: result.overall_score,
                  baseline_score: result.baseline_score,
                  match_score: result.match_score,
                  jd_extraction_status: result.jd_extraction_status,
                  score_breakdown: result.score_breakdown,
                  bullet_point_analysis: result.bullet_point_analysis,
                }, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}

      {/* ── Improver ──────────────────────────────────────────────────── */}
      {showImproveDrawer && (
        <>
          <div
            className="fixed inset-0 z-40 bg-ink/20 animate-fade-in"
            onClick={() => setShowImproveDrawer(false)}
          />

          <div
            role="dialog"
            aria-modal="true"
            aria-label="Resume improver"
            className="fixed left-1/2 top-1/2 z-50 flex h-[80vh] max-h-[720px] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-lg border border-rule bg-surface shadow-md animate-fade-in"
          >
            <div className="flex items-center justify-between gap-4 border-b border-rule px-5 py-3">
              <h2 className="text-base">Resume improver</h2>
              <Toolbar>
                {showDiffViewer && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setShowDiffViewer(false)}
                  >
                    Back to chat
                  </Button>
                )}
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label="Close"
                  onClick={() => setShowImproveDrawer(false)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </Toolbar>
            </div>

            {!showDiffViewer ? (
              <div className="flex flex-1 flex-col overflow-hidden">
                <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
                  {chatMessages.map((msg, i) => (
                    <div
                      key={i}
                      className={
                        msg.role === "user" ? "flex justify-end" : "flex justify-start"
                      }
                    >
                      <div
                        className={`max-w-[85%] whitespace-pre-wrap rounded px-3 py-2 text-sm ${
                          msg.role === "user"
                            ? "bg-ink text-paper"
                            : "bg-sunken text-ink-secondary"
                        }`}
                      >
                        {msg.text}
                      </div>
                    </div>
                  ))}
                  {improving && (
                    <div className="flex items-center gap-2 text-sm text-ink-tertiary">
                      <Spinner />
                      Analysing and improving your resume…
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>

                <div className="space-y-3 border-t border-rule px-5 py-4">
                  {proposedChanges.length === 0 && !improvedResult ? (
                    <Button
                      className="w-full"
                      variant="secondary"
                      onClick={() => handleImprove()}
                      disabled={improving}
                    >
                      Auto-improve — conservative and safe
                    </Button>
                  ) : proposedChanges.length > 0 ? (
                    <Button
                      className="w-full"
                      onClick={() => setShowDiffViewer(true)}
                    >
                      Review and apply {proposedChanges.length} change
                      {proposedChanges.length === 1 ? "" : "s"}
                    </Button>
                  ) : null}

                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleChatSend(); } }}
                      placeholder="Type specific changes, e.g. “Add a professional summary”…"
                      className="h-[34px] flex-1 rounded border border-rule-strong bg-surface px-2.5 text-sm text-ink placeholder:text-ink-tertiary transition-colors duration-100 hover:border-ink-tertiary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25 disabled:bg-sunken"
                      disabled={improving}
                    />
                    <Button
                      size="icon"
                      aria-label="Send"
                      onClick={handleChatSend}
                      disabled={!chatInput.trim() || improving}
                    >
                      <Send className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
                {improvedResult ? (
                  <div className="space-y-2 border-l-2 border-l-good pl-3.5">
                    <div className="flex items-baseline justify-between gap-4">
                      <p className="text-sm text-good">Changes applied and saved</p>
                      {improvedResult.new_score !== undefined && (
                        <span data-numeric className="text-sm text-ink">
                          {improvedResult.new_score}
                          <span className="text-ink-tertiary">/100</span>
                        </span>
                      )}
                    </div>
                    <a
                      href={improvedResult.download_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block text-sm text-accent hover:underline"
                    >
                      Download improved resume (PDF)
                    </a>
                  </div>
                ) : proposedChanges.length > 0 ? (
                  <>
                    <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-rule pb-3">
                      <div>
                        <p className="text-sm font-medium text-ink">
                          {proposedChanges.length} proposed change
                          {proposedChanges.length === 1 ? "" : "s"}
                        </p>
                        <p className="text-xs text-ink-tertiary">
                          {rejectedIndexes.length} rejected,{" "}
                          {proposedChanges.length - rejectedIndexes.length}{" "}
                          accepted
                        </p>
                      </div>
                      <Toolbar>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setRejectedIndexes([])}
                        >
                          Accept all
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            setRejectedIndexes(proposedChanges.map((_, i) => i))
                          }
                        >
                          Reject all
                        </Button>
                        <Button
                          size="sm"
                          onClick={handleApplyChanges}
                          disabled={applying}
                        >
                          {applying && <Spinner className="mr-1.5" />}
                          Apply
                        </Button>
                      </Toolbar>
                    </div>

                    {proposedChanges.map((change, idx) => {
                      const isRejected = rejectedIndexes.includes(idx);
                      return (
                        <div
                          key={idx}
                          className={`border-b border-rule pb-5 ${
                            isRejected ? "opacity-45" : ""
                          }`}
                        >
                          <div className="flex items-baseline justify-between gap-3">
                            <div className="flex items-baseline gap-2">
                              <Tag variant="outline">{change.section}</Tag>
                              <span className="text-xs text-ink-tertiary">
                                {change.category}
                              </span>
                            </div>
                            <button
                              type="button"
                              className="text-sm text-ink-tertiary hover:text-ink hover:underline"
                              onClick={() => {
                                if (isRejected) {
                                  setRejectedIndexes((prev) =>
                                    prev.filter((i) => i !== idx)
                                  );
                                } else {
                                  setRejectedIndexes((prev) => [...prev, idx]);
                                }
                              }}
                            >
                              {change.type === "removed_for_space"
                                ? isRejected
                                  ? "Undo restore"
                                  : "Restore (keep)"
                                : isRejected
                                ? "Undo reject"
                                : "Reject"}
                            </button>
                          </div>

                          <p className="mt-2 text-sm text-ink-tertiary">
                            {change.reason}
                          </p>

                          {change.type === "question" ? (
                            <div className="mt-3 space-y-3 border-l-2 border-l-warn pl-3.5">
                              {change.original && (
                                <p className="text-sm text-ink-secondary">
                                  {change.original}
                                </p>
                              )}
                              <div className="space-y-2">
                                <p className="text-xs uppercase tracking-wide text-warn">
                                  Clarification needed
                                </p>
                                <p className="text-sm text-ink">
                                  {change.proposed}
                                </p>
                                <Textarea
                                  placeholder="Your answer, e.g. “40%”, “500 users”, “3× faster”"
                                  className="min-h-[60px] text-sm"
                                  value={change.user_answer || ""}
                                  onChange={(e) => {
                                    const updated = [...proposedChanges];
                                    updated[idx].user_answer = e.target.value;
                                    setProposedChanges(updated);
                                  }}
                                  disabled={isRejected}
                                />
                              </div>
                            </div>
                          ) : change.type === "removed_for_space" ? (
                            <div className="mt-3 space-y-2 border-l-2 border-l-bad pl-3.5">
                              <p className="text-xs uppercase tracking-wide text-ink-tertiary">
                                Pruned to fit one page
                              </p>
                              <p className="text-sm diff-del">
                                {change.original}
                              </p>
                              <p className="text-xs text-ink-tertiary">
                                Removed to keep the resume on a single page.
                                Restore it above to keep it anyway.
                              </p>
                            </div>
                          ) : (
                            <div className="mt-3 space-y-1.5 text-sm">
                              <p>
                                <span className="text-ink-tertiary">From: </span>
                                {change.original ? (
                                  <span className="diff-del">
                                    {change.original}
                                  </span>
                                ) : (
                                  <span className="text-ink-tertiary">
                                    (empty)
                                  </span>
                                )}
                              </p>
                              <p>
                                <span className="text-ink-tertiary">To: </span>
                                {change.proposed ? (
                                  <span className="diff-add">
                                    {change.proposed}
                                  </span>
                                ) : (
                                  <span className="text-ink-tertiary">
                                    (empty)
                                  </span>
                                )}
                              </p>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </>
                ) : (
                  <EmptyState
                    title="No changes yet"
                    description="Run Auto-improve to analyse the resume and propose edits."
                  />
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
