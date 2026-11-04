"use client";

import { Fragment, useState, useCallback } from "react";
import {
  Section,
  Panel,
  Button,
  Tag,
  Spinner,
  Note,
  Toolbar,
  Table,
  Th,
  Td,
  Tr,
  EmptyState,
  scoreBand,
} from "../components/ui";
import { uploadResume, getResumes, ResumeVersion, addSkillsBatch, deleteResume, deleteAllResumes, renameResume, duplicateResume, API_BASE } from "../lib/api";
import { Trash2, Download, Edit2, Copy, Check, X } from "lucide-react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useTasks } from "../context/TaskContext";

export default function ResumePage() {
  const router = useRouter();

  const {
    uploading,
    uploadResult,
    uploadError,
    uploadFile: file,
    setUploadFile: setFile,
    startUpload,
    resetUpload,
  } = useTasks();

  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resumes, setResumes] = useState<ResumeVersion[]>([]);
  const [expandedResume, setExpandedResume] = useState<string | null>(null);

  // Rename state
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  // New state for manual skill selection
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [savingSkills, setSavingSkills] = useState(false);
  const [skillsSaved, setSkillsSaved] = useState(false);

  // Sync global uploadError to local error
  useEffect(() => {
    if (uploadError) setError(uploadError);
  }, [uploadError]);

  useEffect(() => {
    fetchResumes();
  }, [uploadResult]);

  const fetchResumes = () => {
    getResumes()
      .then(setResumes)
      .catch(() => {});
  };

  const handleDeleteResume = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this resume? This cannot be undone.")) return;

    try {
      await deleteResume(id);
      fetchResumes();
      if (expandedResume === id) {
        setExpandedResume(null);
      }
    } catch (err: any) {
      setError(err.message || "Failed to delete resume");
    }
  };

  const handleDeleteAllResumes = async () => {
    if (!window.confirm("Are you sure you want to delete ALL resumes in your library? This action cannot be undone.")) return;
    try {
      await deleteAllResumes();
      fetchResumes();
      setExpandedResume(null);
    } catch (err: any) {
      setError(err.message || "Failed to delete all resumes");
    }
  };

  const handleRename = async (id: string) => {
    if (!renameValue.trim()) { setRenamingId(null); return; }
    try {
      await renameResume(id, renameValue.trim());
      setResumes(rs => rs.map(r => r.id === id ? { ...r, original_filename: renameValue.trim() } : r));
    } catch (err: any) {
      setError(err.message || "Rename failed");
    } finally {
      setRenamingId(null);
    }
  };

  const handleDuplicate = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await duplicateResume(id);
      fetchResumes();
    } catch (err: any) {
      setError(err.message || "Duplicate failed");
    }
  };

function getFlatSkillsList(skills: any): string[] {
  if (!skills) return [];
  if (Array.isArray(skills)) {
    return skills.map((s: any) => (typeof s === "string" ? s : s?.name || "")).filter(Boolean);
  }
  if (typeof skills === "object") {
    if (Array.isArray(skills.all)) {
      return skills.all.map((s: any) => (typeof s === "string" ? s : s?.name || "")).filter(Boolean);
    }
    const targetObj = skills.byCategory || skills;
    const flat: string[] = [];
    Object.values(targetObj).forEach((val: any) => {
      if (Array.isArray(val)) {
        val.forEach((item: any) => {
          const name = typeof item === "string" ? item : item?.name || "";
          if (name && !flat.includes(name)) flat.push(name);
        });
      } else if (typeof val === "string") {
        val.split(",").forEach((s) => {
          const clean = s.trim();
          if (clean && !flat.includes(clean)) flat.push(clean);
        });
      }
    });
    return flat;
  }
  if (typeof skills === "string") {
    return skills.split(",").map((s) => s.trim()).filter(Boolean);
  }
  return [];
}

  // Sync and normalize skills when uploadResult is available
  useEffect(() => {
    if (uploadResult?.parsed_data?.skills && selectedSkills.length === 0 && !skillsSaved) {
      const flat = getFlatSkillsList(uploadResult.parsed_data.skills);
      setSelectedSkills(flat);
    }
  }, [uploadResult, selectedSkills.length, skillsSaved]);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      validateAndSetFile(droppedFile);
    }
  }, []);

  const validateAndSetFile = (f: File) => {
    setError(null);
    resetUpload();

    const validTypes = [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "image/png",
      "image/jpeg",
      "image/jpg",
    ];
    const isImage = f.type.startsWith("image/") || f.name.endsWith(".png") || f.name.endsWith(".jpg") || f.name.endsWith(".jpeg");
    if (!validTypes.includes(f.type) && !f.name.endsWith(".pdf") && !f.name.endsWith(".docx") && !isImage) {
      setError("Only PDF, DOCX, and images (PNG, JPG) are supported.");
      return;
    }
    if (f.size > 10 * 1024 * 1024) {
      setError("File must be under 10MB.");
      return;
    }
    setFile(f);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setError(null);

    try {
      setSkillsSaved(false);
      setSelectedSkills([]);
      await startUpload(file);
    } catch (err: any) {
      setError(err.message || "Upload failed. Is the backend running?");
    }
  };

  const handleToggleSkill = (skillName: string) => {
    setSelectedSkills(prev =>
      prev.includes(skillName)
        ? prev.filter(s => s !== skillName)
        : [...prev, skillName]
    );
  };

  const handleSaveSkills = async () => {
    if (selectedSkills.length === 0 || !uploadResult?.resume_id) return;

    setSavingSkills(true);
    try {
      await addSkillsBatch(selectedSkills, uploadResult.resume_id);
      setSkillsSaved(true);
    } catch (err: any) {
      setError(err.message || "Failed to save skills.");
    } finally {
      setSavingSkills(false);
    }
  };

  return (
    <div className="space-y-12 pb-20">
      <header>
        <h1 className="text-3xl">Resumes</h1>
        <p className="mt-1.5 text-sm text-ink-tertiary">
          Upload a resume to extract skills and experience, then track versions
          over time.
        </p>
      </header>

      {/* ── Upload ────────────────────────────────────────────────────── */}
      <Section title="Upload">
        <div className="space-y-4">
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => document.getElementById("file-input")?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center border border-dashed px-6 py-14 text-center transition-colors duration-100 ${
              dragActive
                ? "border-accent bg-accent/[0.04]"
                : "border-rule-strong hover:border-ink-tertiary hover:bg-sunken"
            }`}
          >
            <input
              id="file-input"
              type="file"
              accept=".pdf,.docx,.png,.jpg,.jpeg"
              onChange={handleFileChange}
              className="hidden"
            />
            <p className="font-serif text-lg text-ink">
              {file ? file.name : "Drop a resume here, or click to browse"}
            </p>
            <p className="mt-1.5 text-sm text-ink-tertiary">
              PDF, DOCX, PNG or JPG — up to 10 MB
            </p>
          </div>

          {file && (
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule pb-4">
              <div className="min-w-0">
                <p className="truncate text-sm text-ink">{file.name}</p>
                <p className="text-xs text-ink-tertiary" data-numeric>
                  {(file.size / 1024).toFixed(1)} KB
                </p>
              </div>
              <Button onClick={handleUpload} disabled={uploading}>
                {uploading ? (
                  <>
                    <Spinner className="mr-1.5" />
                    Parsing…
                  </>
                ) : (
                  "Analyse resume"
                )}
              </Button>
            </div>
          )}

          {error && <Note variant="bad">{error}</Note>}

          {uploadResult && (
            <Note variant="good">
              <span className="flex items-center justify-between gap-4">
                Resume parsed. Review the extracted data below.
                <button
                  type="button"
                  onClick={() => {
                    resetUpload();
                    setSelectedSkills([]);
                    setSkillsSaved(false);
                  }}
                  className="shrink-0 text-ink-tertiary hover:text-ink hover:underline"
                >
                  Dismiss
                </button>
              </span>
            </Note>
          )}
        </div>
      </Section>

      {/* ── Parsed preview ────────────────────────────────────────────── */}
      {uploadResult?.parsed_data && (
        <Section
          title="Parsed data"
          description="What was extracted from the document."
          action={
            <button
              type="button"
              onClick={() => {
                resetUpload();
                setSelectedSkills([]);
                setSkillsSaved(false);
              }}
              className="text-sm text-ink-tertiary hover:text-bad hover:underline"
            >
              Discard
            </button>
          }
        >
          <div className="space-y-8">
            {/* Contact info */}
            {uploadResult.parsed_data.contact_info && (
              <div>
                <p className="mb-2 text-xs uppercase tracking-wide text-ink-tertiary">
                  Contact
                </p>
                <dl className="grid gap-x-8 sm:grid-cols-2">
                  {Object.entries(uploadResult.parsed_data.contact_info).map(
                    ([key, value]: [string, any]) =>
                      value && (
                        <div
                          key={key}
                          className="flex items-baseline justify-between gap-3 border-b border-rule py-2 text-sm"
                        >
                          <dt className="capitalize text-ink-tertiary">{key}</dt>
                          <dd className="truncate text-ink">{String(value)}</dd>
                        </div>
                      )
                  )}
                </dl>
              </div>
            )}

            {/* Skills */}
            {uploadResult.parsed_data.skills && (
              <div>
                <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
                  <p className="text-xs uppercase tracking-wide text-ink-tertiary">
                    Skills detected — click to select
                  </p>
                  {skillsSaved ? (
                    <span className="text-sm text-good">Saved</span>
                  ) : (
                    <Toolbar>
                      {selectedSkills.length > 0 ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setSelectedSkills([])}
                        >
                          Deselect all
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            const flat = getFlatSkillsList(
                              uploadResult.parsed_data.skills
                            );
                            setSelectedSkills(flat);
                          }}
                        >
                          Select all
                        </Button>
                      )}
                      <Button
                        size="sm"
                        onClick={handleSaveSkills}
                        disabled={savingSkills || selectedSkills.length === 0}
                      >
                        {savingSkills && <Spinner className="mr-1.5" />}
                        Save {selectedSkills.length} skill
                        {selectedSkills.length === 1 ? "" : "s"}
                      </Button>
                    </Toolbar>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {getFlatSkillsList(uploadResult.parsed_data.skills).map(
                    (skillName: string, i: number) => {
                      const isSelected = selectedSkills.includes(skillName);
                      return (
                        <button
                          key={i}
                          type="button"
                          disabled={skillsSaved}
                          onClick={() =>
                            !skillsSaved && handleToggleSkill(skillName)
                          }
                          className={`rounded border px-1.5 py-0.5 text-xs font-medium leading-4 transition-colors duration-100 disabled:cursor-default ${
                            isSelected
                              ? "border-ink bg-ink text-paper"
                              : "border-rule bg-surface text-ink-tertiary hover:border-ink-tertiary hover:text-ink"
                          }`}
                        >
                          {skillName}
                        </button>
                      );
                    }
                  )}
                </div>
              </div>
            )}

            {/* Experience */}
            {uploadResult.parsed_data.experience && (
              <div>
                <p className="mb-2 text-xs uppercase tracking-wide text-ink-tertiary">
                  Experience
                </p>
                <ul>
                  {uploadResult.parsed_data.experience.map(
                    (exp: any, i: number) => (
                      <li
                        key={i}
                        className="flex flex-wrap items-baseline justify-between gap-x-4 border-b border-rule py-2.5"
                      >
                        <span className="text-sm text-ink">
                          {exp.title || exp.role || "Untitled"}
                          {exp.company && (
                            <span className="text-ink-tertiary">
                              {" "}
                              — {exp.company}
                            </span>
                          )}
                        </span>
                        <span className="text-sm text-ink-tertiary">
                          {exp.dates ||
                            (exp.start_date || exp.startDate
                              ? `${exp.start_date || exp.startDate} – ${
                                  exp.end_date || exp.endDate || "Present"
                                }`
                              : "")}
                        </span>
                      </li>
                    )
                  )}
                </ul>
              </div>
            )}
          </div>
        </Section>
      )}

      {/* ── Library ───────────────────────────────────────────────────── */}
      <Section
        title="Versions"
        description={
          resumes.length > 0
            ? `${resumes.length} document${resumes.length === 1 ? "" : "s"} in history`
            : undefined
        }
        action={
          resumes.length > 0 ? (
            <button
              type="button"
              onClick={handleDeleteAllResumes}
              className="text-sm text-ink-tertiary hover:text-bad hover:underline"
            >
              Delete all
            </button>
          ) : undefined
        }
      >
        {resumes.length === 0 ? (
          <EmptyState
            title="No versions yet"
            description="Every resume you upload or improve is kept here so you can compare scores over time."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>File</Th>
                <Th className="w-[120px]">Source</Th>
                <Th className="w-[80px] text-right">Score</Th>
                <Th className="w-[140px]">Date</Th>
                <Th className="w-[110px] text-right">Actions</Th>
              </tr>
            </thead>
            <tbody>
              {resumes.map((resume) => {
                const isOpen = expandedResume === resume.id;
                const rowScore =
                  typeof resume.structured_json?.score === "number"
                    ? resume.structured_json.score
                    : null;
                return (
                  <Fragment key={resume.id}>
                    <Tr>
                      <Td className="max-w-0">
                        {renamingId === resume.id ? (
                          <form
                            onSubmit={(e) => { e.preventDefault(); handleRename(resume.id); }}
                            className="flex items-center gap-1"
                          >
                            <input
                              autoFocus
                              value={renameValue}
                              onChange={e => setRenameValue(e.target.value)}
                              onBlur={() => handleRename(resume.id)}
                              className="w-full border-b border-accent bg-transparent text-sm text-ink outline-none"
                            />
                            <button type="submit" className="text-accent"><Check className="h-3 w-3" /></button>
                            <button type="button" onClick={() => setRenamingId(null)} className="text-ink-tertiary"><X className="h-3 w-3" /></button>
                          </form>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setExpandedResume(isOpen ? null : resume.id)}
                            aria-expanded={isOpen}
                            className="block w-full truncate text-left text-ink hover:text-accent"
                          >
                            {resume.original_filename || "Resume"}
                          </button>
                        )}
                      </Td>
                      <Td>
                        <Tag>{resume.source}</Tag>
                      </Td>
                      <Td className="text-right">
                        {rowScore !== null ? (
                          <span data-numeric className={scoreBand(rowScore).text}>
                            {rowScore}
                          </span>
                        ) : (
                          <span className="text-rule-strong">—</span>
                        )}
                      </Td>
                      <Td>
                        <time className="text-ink-tertiary">
                          {new Date(resume.created_at).toLocaleDateString()}
                        </time>
                      </Td>
                      <Td>
                        <div className="flex items-center justify-end gap-1">
                          {/* Rename */}
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); setRenameValue(resume.original_filename || "Resume"); setRenamingId(resume.id); }}
                            title="Rename"
                            className="rounded p-1 text-ink-tertiary transition-colors hover:bg-sunken hover:text-ink"
                          >
                            <Edit2 className="h-3.5 w-3.5" />
                          </button>
                          {/* Duplicate */}
                          <button
                            type="button"
                            onClick={(e) => handleDuplicate(resume.id, e)}
                            title="Duplicate"
                            className="rounded p-1 text-ink-tertiary transition-colors hover:bg-sunken hover:text-ink"
                          >
                            <Copy className="h-3.5 w-3.5" />
                          </button>
                          {/* Open in Builder — for builder-created or uploaded resumes */}
                          {(resume.source === "builder" || resume.source === "uploaded") && (
                            <button
                              type="button"
                              onClick={() => router.push(`/builder?id=${resume.id}`)}
                              title="Open in Builder"
                              className="rounded p-1 text-ink-tertiary transition-colors hover:bg-sunken hover:text-accent"
                            >
                              <Edit2 className="h-3.5 w-3.5" />
                            </button>
                          )}
                          <a
                            href={`${API_BASE}/resumes/${resume.id}/original`}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="Open original"
                            className="rounded p-1 text-ink-tertiary transition-colors hover:bg-sunken hover:text-ink"
                          >
                            <Download className="h-3.5 w-3.5" />
                          </a>
                          <button
                            type="button"
                            onClick={(e) => handleDeleteResume(resume.id, e)}
                            title="Delete resume"
                            className="rounded p-1 text-ink-tertiary transition-colors hover:bg-sunken hover:text-bad"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </Td>
                    </Tr>
                    {isOpen && (
                      <tr>
                        <td colSpan={5} className="border-b border-rule p-0">
                          <pre className="overflow-x-auto whitespace-pre-wrap bg-sunken p-4 font-mono text-xs leading-relaxed text-ink-secondary">
                            {JSON.stringify(resume.structured_json, null, 2)}
                          </pre>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </Table>
        )}
      </Section>
    </div>
  );
}
