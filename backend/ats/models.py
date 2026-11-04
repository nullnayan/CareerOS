from dataclasses import dataclass
from typing import Literal, Mapping, Any, Optional

Seniority = Literal["student", "entry", "mid", "senior", "exec"]
Dimension = Literal["IMPACT", "BREVITY", "STYLE", "STRUCTURE", "FORMATTING", "AUTHENTICITY", "GROWTH", "MATCH"]

@dataclass(frozen=True)
class Contact:
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    location: Optional[str]
    links: tuple[str, ...]

@dataclass(frozen=True)
class Experience:
    company: str
    title: str
    start_date: str
    end_date: str
    is_current: bool
    bullets: tuple[str, ...]
    description: str

@dataclass(frozen=True)
class Education:
    institution: str
    degree: str
    field: str
    end_year: str
    gpa: str

@dataclass(frozen=True)
class Project:
    name: str
    bullets: tuple[str, ...]
    description: str
    technologies: tuple[str, ...]

@dataclass(frozen=True)
class Skill:
    name: str
    category: str

@dataclass(frozen=True)
class Certification:
    name: str

@dataclass(frozen=True)
class Bullet:
    text: str
    section: Literal["experience", "projects", "volunteer"]
    entry_index: int
    bullet_index: int
    entry_is_current: bool

@dataclass(frozen=True)
class TextViews:
    bullets: tuple[Bullet, ...]
    by_section: Mapping[str, str]
    full: str
    layout_raw: str

@dataclass(frozen=True)
class LayoutFacts:
    page_count: int
    has_columns: bool
    has_tables: bool
    is_scanned: bool
    embedded_fonts: tuple[str, ...]
    font_sizes_by_section: Mapping[str, tuple[float, ...]]
    has_images: bool
    header_footer_text: tuple[str, ...]
    file_type: str

@dataclass(frozen=True)
class CandidateProfile:
    seniority: Seniority
    years_experience: float
    domain: str
    has_formal_experience: bool

@dataclass(frozen=True)
class JDKeyword:
    term: str
    skill_id: str | None
    kind: str
    jd_frequency: int
    required: bool

@dataclass(frozen=True)
class JobTarget:
    title: str
    title_normalized: str
    seniority: str
    keywords: tuple[JDKeyword, ...]
    min_years: float | None
    required_degree: str | None
    source_hash: str
    extraction_confidence: str = "ok"  # "ok" | "low" | "failed"

@dataclass(frozen=True)
class ResumeDoc:
    contact: Contact
    summary: str
    experience: tuple[Experience, ...]
    education: tuple[Education, ...]
    projects: tuple[Project, ...]
    skills: tuple[Skill, ...]
    certifications: tuple[Certification, ...]
    text: TextViews
    layout: LayoutFacts
    profile: CandidateProfile

@dataclass(frozen=True)
class Anchor:
    section: str
    entry_index: int
    bullet_index: int

@dataclass(frozen=True)
class Fix:
    kind: Literal["transform", "guidance"]
    description: str
    apply: Any | None  # Callable[[ResumeDoc], ResumeDoc] | None
    target: Optional[Anchor]

@dataclass
class Finding:
    check_id: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    title: str
    detail: str
    anchor: Optional[Anchor]
    fix: Optional[Fix]
    points: float = 0.0

@dataclass(frozen=True)
class CheckResult:
    check_id: str
    score: float | None
    findings: tuple[Finding, ...]
    evidence: Mapping[str, Any]
