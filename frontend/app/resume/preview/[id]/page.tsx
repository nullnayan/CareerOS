"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getResumeById } from "../../../lib/api";

interface ResumeData {
  name?: string;
  email?: string;
  phone?: string;
  location?: string;
  linkedin?: string;
  github?: string;
  portfolio?: string;
  summary?: string;
  experience?: {
    title?: string;
    role?: string;
    company?: string;
    start_date?: string;
    end_date?: string;
    location?: string;
    bullet_points?: string[];
  }[];
  education?: {
    degree?: string;
    field?: string;
    institution?: string;
    graduation_date?: string;
    gpa?: string;
  }[];
  skills?: (string | { name?: string; category?: string })[];
  projects?: {
    name?: string;
    description?: string;
    technologies?: string[];
    url?: string;
  }[];
  certifications?: {
    name?: string;
    issuer?: string;
    date?: string;
  }[];
}

export default function ResumePreviewPage() {
  const params = useParams();
  const resumeId = params.id as string;
  const [resume, setResume] = useState<ResumeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!resumeId) return;
    getResumeById(resumeId)
      .then((res) => {
        setResume(res.structured_json as ResumeData);
      })
      .catch((err) => setError(err.message || "Failed to load resume"))
      .finally(() => setLoading(false));
  }, [resumeId]);

  const handlePrint = () => {
    window.print();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-center space-y-3">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto" />
          <p className="text-sm text-gray-500">Loading resume...</p>
        </div>
      </div>
    );
  }

  if (error || !resume) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-center space-y-3">
          <p className="text-red-600 font-medium">Failed to load resume</p>
          <p className="text-sm text-gray-500">{error}</p>
        </div>
      </div>
    );
  }

  // Flatten skills to strings
  const skillStrings: string[] = Array.isArray(resume.skills) ? (resume.skills || []).map((s) =>
    typeof s === "string" ? s : s.name || ""
  ).filter(Boolean) : [];

  // Group skills by category if available
  const groupedSkills: Record<string, string[]> = {};
  if (Array.isArray(resume.skills)) {
    (resume.skills || []).forEach((s) => {
      if (typeof s === "object" && s.category) {
        if (!groupedSkills[s.category]) groupedSkills[s.category] = [];
        groupedSkills[s.category].push(s.name || "");
      }
    });
  }
  const hasGroupedSkills = Object.keys(groupedSkills).length > 0;

  // Gather contact details safely supporting both nested and flat schemas
  const contactObj = (resume as any).contact || {};
  const name = resume.name || contactObj.name || "Your Name";
  const email = resume.email || contactObj.email;
  const phone = resume.phone || contactObj.phone;
  
  const location = resume.location || 
    (typeof contactObj.location === "string" ? contactObj.location : contactObj.location?.raw);

  const links = Array.isArray(contactObj.links) ? contactObj.links : [];
  const linkedin = resume.linkedin || contactObj.linkedin || links.find((l: string) => typeof l === "string" && l.includes("linkedin.com"));
  const github = resume.github || contactObj.github || links.find((l: string) => typeof l === "string" && l.includes("github.com"));
  const portfolio = resume.portfolio || contactObj.portfolio || links.find((l: string) => typeof l === "string" && !l.includes("linkedin.com") && !l.includes("github.com"));

  return (
    <>
      {/* Print Styles */}
      <style jsx global>{`
        @media print {
          body * {
            visibility: hidden;
          }
          #resume-document,
          #resume-document * {
            visibility: visible;
          }
          #resume-document {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            margin: 0;
            padding: 0.5in 0.6in;
            box-shadow: none !important;
            border: none !important;
          }
          #print-controls {
            display: none !important;
          }
          @page {
            margin: 0.3in;
            size: letter;
          }
        }
        
        #resume-document {
          font-family: 'Georgia', 'Times New Roman', serif;
          color: #1a1a1a;
          line-height: 1.45;
        }
        #resume-document h1 {
          font-size: 22px;
          font-weight: 700;
          letter-spacing: 0.5px;
          margin: 0;
        }
        #resume-document h2 {
          font-size: 13px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 1.2px;
          border-bottom: 1.5px solid #1a1a1a;
          padding-bottom: 3px;
          margin: 16px 0 8px 0;
        }
        #resume-document h3 {
          font-size: 12.5px;
          font-weight: 700;
          margin: 0;
        }
        #resume-document p,
        #resume-document li,
        #resume-document span {
          font-size: 11.5px;
        }
        #resume-document ul {
          margin: 3px 0 0 0;
          padding-left: 18px;
        }
        #resume-document li {
          margin-bottom: 2px;
          line-height: 1.4;
        }
      `}</style>

      {/* Print Controls Bar */}
      <div
        id="print-controls"
        className="sticky top-0 z-50 bg-white border-b border-gray-200 shadow-sm"
      >
        <div className="max-w-[850px] mx-auto flex items-center justify-between px-6 py-3">
          <div>
            <h1 className="text-sm font-semibold text-gray-900">
              Resume Preview
            </h1>
            <p className="text-xs text-gray-500">
              ATS-optimized format • Ready to download
            </p>
          </div>
          <button
            onClick={handlePrint}
            className="inline-flex items-center gap-2 rounded-lg bg-gray-900 text-white text-sm font-medium px-5 py-2.5 hover:bg-gray-800 transition-colors shadow-sm"
          >
            <svg
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
            Save as PDF
          </button>
        </div>
      </div>

      {/* Resume Document */}
      <div className="min-h-screen bg-gray-100 py-8 px-4">
        <div
          id="resume-document"
          className="max-w-[850px] mx-auto bg-white shadow-lg rounded-sm"
          style={{ padding: "0.6in 0.7in" }}
        >
          {/* Header / Contact */}
          <div className="text-center mb-1">
            <h1>{name}</h1>
            <div
              className="flex flex-wrap items-center justify-center gap-x-3 mt-1"
              style={{ fontSize: "11px", color: "#555" }}
            >
              {email && <span>{email}</span>}
              {phone && (
                <>
                  <span>•</span>
                  <span>{phone}</span>
                </>
              )}
              {location && (
                <>
                  <span>•</span>
                  <span>{location}</span>
                </>
              )}
              {linkedin && (
                <>
                  <span>•</span>
                  <span>
                    <a href={linkedin} target="_blank" rel="noopener noreferrer" className="hover:underline">
                      LinkedIn
                    </a>
                  </span>
                </>
              )}
              {github && (
                <>
                  <span>•</span>
                  <span>
                    <a href={github} target="_blank" rel="noopener noreferrer" className="hover:underline">
                      GitHub
                    </a>
                  </span>
                </>
              )}
              {portfolio && (
                <>
                  <span>•</span>
                  <span>
                    <a href={portfolio} target="_blank" rel="noopener noreferrer" className="hover:underline">
                      Portfolio
                    </a>
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Summary */}
          {resume.summary && (
            <div>
              <h2>Professional Summary</h2>
              <p style={{ textAlign: "justify" }}>{resume.summary}</p>
            </div>
          )}

          {/* Experience */}
          {resume.experience && Array.isArray(resume.experience) && resume.experience.length > 0 && (
            <div>
              <h2>Experience</h2>
              {resume.experience.map((exp, i) => (
                <div key={i} style={{ marginBottom: "10px" }}>
                  <div className="flex items-start justify-between">
                    <div>
                      <h3>
                        {exp.title || exp.role || "Role"}{" "}
                        <span style={{ fontWeight: 400 }}>
                          | {exp.company || "Company"}
                        </span>
                      </h3>
                    </div>
                    <span
                      style={{
                        fontSize: "11px",
                        color: "#555",
                        whiteSpace: "nowrap",
                        marginLeft: "12px",
                      }}
                    >
                      {[exp.start_date, exp.end_date]
                        .filter(Boolean)
                        .join(" – ")}
                      {exp.location ? ` | ${exp.location}` : ""}
                    </span>
                  </div>
                  {exp.bullet_points && Array.isArray(exp.bullet_points) && exp.bullet_points.length > 0 && (
                    <ul>
                      {exp.bullet_points.map((bp, j) => (
                        <li key={j}>{bp}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Education */}
          {resume.education && Array.isArray(resume.education) && resume.education.length > 0 && (
            <div>
              <h2>Education</h2>
              {resume.education.map((edu: any, i) => (
                <div key={i} style={{ marginBottom: "6px" }}>
                  <div className="flex items-start justify-between">
                    <h3>
                      {edu.degree}
                      {edu.field ? ` in ${edu.field}` : ""}
                      {edu.institution
                        ? ` — ${edu.institution}`
                        : ""}
                    </h3>
                    <span
                      style={{
                        fontSize: "11px",
                        color: "#555",
                        whiteSpace: "nowrap",
                        marginLeft: "12px",
                      }}
                    >
                      {edu.graduation_date || ""}
                      {edu.gpa || edu.cgpa_or_percentage ? ` | GPA: ${edu.gpa || edu.cgpa_or_percentage}` : ""}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Skills */}
          {skillStrings.length > 0 && (
            <div>
              <h2>Skills</h2>
              {hasGroupedSkills ? (
                <div>
                  {Object.entries(groupedSkills).map(([category, skills]) => (
                    <p key={category} style={{ marginBottom: "3px" }}>
                      <strong>{category}:</strong> {skills.join(", ")}
                    </p>
                  ))}
                </div>
              ) : (
                <p>{skillStrings.join(" • ")}</p>
              )}
            </div>
          )}

          {/* Projects */}
          {resume.projects && (Array.isArray(resume.projects) ? resume.projects.length > 0 : typeof (resume.projects as any) === "string" && (resume.projects as any).trim()) && (
            <div>
              <h2>Projects</h2>
              {Array.isArray(resume.projects) ? (
                resume.projects.map((proj: any, i) => (
                  <div key={i} style={{ marginBottom: "8px" }}>
                    <h3>
                      {proj.name || "Project"}
                      {proj.technologies && Array.isArray(proj.technologies) && proj.technologies.length > 0 && (
                        <span style={{ fontWeight: 400, fontSize: "11px" }}>
                          {" "}
                          | {proj.technologies.join(", ")}
                        </span>
                      )}
                    </h3>
                    {proj.description && (
                      <p style={{ margin: "2px 0 0 0" }}>{proj.description}</p>
                    )}
                    {proj.bullets && Array.isArray(proj.bullets) && proj.bullets.length > 0 && (
                      <ul style={{ listStyleType: "disc", paddingLeft: "18px", marginTop: "3px" }}>
                        {proj.bullets.map((bullet: string, j: number) => (
                          <li key={j}>{bullet}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))
              ) : (
                <p style={{ whiteSpace: "pre-line" }}>{resume.projects}</p>
              )}
            </div>
          )}

          {/* Certifications */}
          {resume.certifications && (Array.isArray(resume.certifications) ? resume.certifications.length > 0 : typeof (resume.certifications as any) === "string" && (resume.certifications as any).trim()) && (
            <div>
              <h2>Certifications</h2>
              {Array.isArray(resume.certifications) ? (
                resume.certifications.map((cert: any, i) => {
                  const certName = typeof cert === "string" ? cert : cert.name || "";
                  const certIssuer = typeof cert === "string" ? "" : cert.issuer || "";
                  const certDate = typeof cert === "string" ? "" : cert.date || "";
                  return (
                    <p key={i} style={{ marginBottom: "3px" }}>
                      <strong>{certName}</strong>
                      {certIssuer ? ` — ${certIssuer}` : ""}
                      {certDate ? ` (${certDate})` : ""}
                    </p>
                  );
                })
              ) : (
                <p style={{ whiteSpace: "pre-line" }}>{resume.certifications}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
