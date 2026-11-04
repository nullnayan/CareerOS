"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Download, Trash2 } from "lucide-react";
import {
  Section,
  Stat,
  StatRow,
  Table,
  Th,
  Td,
  Tr,
  Toolbar,
  Button,
  EmptyState,
  Spinner,
  Tag,
  scoreBand,
} from "./components/ui";
import {
  getSkills,
  getSuggestions,
  getResumes,
  deleteResume,
  getGitHubStatus,
  connectGitHub,
  getTailorSessions,
  TailorSession,
  ResumeVersion,
  API_BASE,
} from "./lib/api";

const TRACKING_START_DATE = new Date("2026-07-16T17:15:19Z");

const API_ORIGIN = API_BASE;

/** One row of the merged activity table. */
type ActivityRow = {
  key: string;
  kind: "Resume" | "Tailored";
  name: string;
  score: number | null;
  date: string | null;
  href: string;
  onDelete?: (e: React.MouseEvent) => void;
};

function formatDate(value: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function DashboardPage() {
  const router = useRouter();
  const [skillCount, setSkillCount] = useState<number | null>(null);
  const [suggestionCount, setSuggestionCount] = useState<number | null>(null);
  const [resumeCount, setResumeCount] = useState<number | null>(null);
  const [bestResumes, setBestResumes] = useState<ResumeVersion[]>([]);
  const [recentResumes, setRecentResumes] = useState<ResumeVersion[]>([]);
  const [gitStatus, setGitStatus] = useState<{
    connected: boolean;
    github_username: string | null;
  } | null>(null);
  const [tailoredSessions, setTailoredSessions] = useState<TailorSession[]>([]);

  const handleDeleteResume = async (resumeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (
      !confirm(
        "Are you sure you want to delete this resume version? This will permanently remove it from history."
      )
    ) {
      return;
    }
    try {
      await deleteResume(resumeId);
      setBestResumes((prev) => prev.filter((r) => r.id !== resumeId));
      setRecentResumes((prev) => prev.filter((r) => r.id !== resumeId));
      setResumeCount((prev) => (prev !== null ? Math.max(0, prev - 1) : null));
    } catch (err: any) {
      alert("Failed to delete resume: " + err.message);
    }
  };

  const handleConnectGit = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const res = await connectGitHub();
      if (res.auth_url) {
        window.location.href = res.auth_url;
      }
    } catch (err: any) {
      alert("Failed to connect GitHub: " + err.message);
    }
  };

  useEffect(() => {
    // Load dashboard data
    getSkills()
      .then((skills) => setSkillCount(skills.length))
      .catch(() => setSkillCount(0));

    getSuggestions("pending")
      .then((suggestions) => setSuggestionCount(suggestions.length))
      .catch(() => setSuggestionCount(0));

    getGitHubStatus()
      .then((status) => setGitStatus(status))
      .catch(() => setGitStatus({ connected: false, github_username: null }));

    getTailorSessions()
      .then((s) => setTailoredSessions(s))
      .catch(() => setTailoredSessions([]));

    getResumes()
      .then((resumes) => {
        setResumeCount(resumes.length);

        setRecentResumes(
          [...resumes]
            .sort(
              (a, b) =>
                new Date(b.created_at).getTime() -
                new Date(a.created_at).getTime()
            )
            .slice(0, 5)
        );

        // Find top 3 unique resumes with the highest ATS scores
        const validResumes = resumes.filter((r) => {
          return (
            new Date(r.created_at) >= TRACKING_START_DATE &&
            r.structured_json &&
            typeof r.structured_json.score === "number"
          );
        });

        if (validResumes.length > 0) {
          // Deduplicate by filename (keep the highest score one per unique filename)
          const bestPerFile = new Map<string, ResumeVersion>();
          for (const r of validResumes) {
            const key = r.original_filename || r.id;
            const existing = bestPerFile.get(key);
            if (
              !existing ||
              r.structured_json.score > existing.structured_json.score
            ) {
              bestPerFile.set(key, r);
            }
          }

          // Sort by score descending
          const sorted = Array.from(bestPerFile.values()).sort(
            (a, b) => b.structured_json.score - a.structured_json.score
          );

          setBestResumes(sorted.slice(0, 3));
        } else {
          setBestResumes([]);
        }
      })
      .catch(() => {
        setResumeCount(0);
        setBestResumes([]);
        setRecentResumes([]);
      });
  }, []);

  // Resumes and tailored sessions read as one stream of work, newest first.
  const activity = useMemo<ActivityRow[]>(() => {
    const rows: ActivityRow[] = [
      ...recentResumes.map((r) => ({
        key: `resume-${r.id}`,
        kind: "Resume" as const,
        name: r.original_filename || "Untitled resume",
        score:
          typeof r.structured_json?.score === "number"
            ? r.structured_json.score
            : null,
        date: r.created_at,
        href: `${API_ORIGIN}/resumes/${r.id}/original`,
        onDelete: (e: React.MouseEvent) => handleDeleteResume(r.id, e),
      })),
      ...tailoredSessions.map((s) => ({
        key: `tailor-${s.id}`,
        kind: "Tailored" as const,
        name: s.label,
        score: s.score,
        date: s.created_at,
        href: s.download_pdf_url,
      })),
    ];

    return rows
      .sort(
        (a, b) =>
          new Date(b.date ?? 0).getTime() - new Date(a.date ?? 0).getTime()
      )
      .slice(0, 8);
  }, [recentResumes, tailoredSessions]);

  const lastActivity = activity[0];
  const bestScore = bestResumes[0]?.structured_json?.score ?? null;

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-3xl">Overview</h1>
        <p className="mt-1.5 text-sm text-ink-tertiary">
          {lastActivity
            ? `Last activity — ${lastActivity.kind === "Tailored" ? "tailored" : "uploaded"} ${lastActivity.name} on ${formatDate(lastActivity.date)}.`
            : "No activity yet. Upload a resume to get started."}
        </p>
      </header>

      <StatRow>
        <Stat
          label="Best ATS score"
          value={bestScore !== null ? bestScore : "—"}
          hint={
            bestResumes[0]
              ? bestResumes[0].original_filename || "Resume"
              : "No scores tracked yet"
          }
        />
        <Stat
          label="Resumes"
          value={resumeCount !== null ? resumeCount : <Spinner />}
          hint="Versions in history"
        />
        <Stat
          label="Skills"
          value={skillCount !== null ? skillCount : <Spinner />}
          hint={
            suggestionCount !== null && suggestionCount > 0
              ? `${suggestionCount} pending suggestion${suggestionCount === 1 ? "" : "s"}`
              : "Verified inventory"
          }
        />
        <Stat
          label="GitHub"
          value={
            gitStatus === null ? (
              <Spinner />
            ) : gitStatus.connected ? (
              <span className="truncate text-xl">
                @{gitStatus.github_username}
              </span>
            ) : (
              <span className="text-xl text-ink-tertiary">Not connected</span>
            )
          }
          hint={
            gitStatus?.connected ? (
              <Link href="/github" className="text-accent">
                Manage connection
              </Link>
            ) : (
              <button
                type="button"
                onClick={handleConnectGit}
                className="text-accent hover:underline"
              >
                Connect account
              </button>
            )
          }
        />
      </StatRow>

      <Toolbar>
        <Button onClick={() => router.push("/resume")}>Upload resume</Button>
        <Button variant="secondary" onClick={() => router.push("/ats")}>
          Run ATS check
        </Button>
        <Button variant="secondary" onClick={() => router.push("/tailor")}>
          Tailor to a job
        </Button>
        <Button variant="ghost" onClick={() => router.push("/skills")}>
          Manage skills
        </Button>
      </Toolbar>

      <Section
        title="Recent activity"
        action={
          <Link href="/resume" className="text-sm text-accent">
            All resumes
          </Link>
        }
      >
        {activity.length === 0 ? (
          <EmptyState
            title="Nothing here yet"
            description="Upload a resume to score it against a job description and track versions over time."
            action={
              <Button onClick={() => router.push("/resume")}>
                Upload resume
              </Button>
            }
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th className="w-[110px]">Type</Th>
                <Th className="w-[90px] text-right">Score</Th>
                <Th className="w-[140px]">Date</Th>
                <Th className="w-[90px] text-right">Actions</Th>
              </tr>
            </thead>
            <tbody>
              {activity.map((row) => (
                <Tr key={row.key}>
                  <Td className="max-w-0">
                    <a
                      href={row.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block truncate text-ink hover:text-accent"
                    >
                      {row.name}
                    </a>
                  </Td>
                  <Td>
                    <Tag variant={row.kind === "Tailored" ? "accent" : "default"}>
                      {row.kind}
                    </Tag>
                  </Td>
                  <Td className="text-right">
                    {row.score !== null ? (
                      <span
                        data-numeric
                        className={scoreBand(row.score).text}
                      >
                        {row.score}
                      </span>
                    ) : (
                      <span className="text-rule-strong">—</span>
                    )}
                  </Td>
                  <Td>
                    <time className="text-ink-tertiary">
                      {formatDate(row.date)}
                    </time>
                  </Td>
                  <Td>
                    <div className="flex items-center justify-end gap-1">
                      <a
                        href={row.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        title="Download"
                        className="rounded p-1 text-ink-tertiary transition-colors hover:bg-sunken hover:text-ink"
                      >
                        <Download className="h-3.5 w-3.5" />
                      </a>
                      {row.onDelete && (
                        <button
                          type="button"
                          onClick={row.onDelete}
                          title="Delete version"
                          className="rounded p-1 text-ink-tertiary transition-colors hover:bg-sunken hover:text-bad"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Section>
    </div>
  );
}
