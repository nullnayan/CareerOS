"""
backend/schemas/resume.py
==========================
Canonical Resume JSON schema for CareerOS.

This is the single source of truth for the resume data shape.
All consumers (builder frontend, Jinja templates, AI agents, ATS scorer)
must read and write this shape.

schema_version = 1
"""

from pydantic import BaseModel, Field
from typing import Optional


# ─── Sub-models ────────────────────────────────────────────────────────────────

class CustomField(BaseModel):
    id: str = ""
    label: str = ""
    value: str = ""

class Contact(BaseModel):
    name: str = ""
    headline: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    website: str = ""
    custom_fields: list[CustomField] = Field(default_factory=list)

class ProfileLink(BaseModel):
    id: str = ""
    network: str = ""   # e.g. "GitHub", "LinkedIn"
    username: str = ""
    url: str = ""
    hidden: bool = False

class Photo(BaseModel):
    url: str = ""       # server-relative path or data URI (only at render time)
    hidden: bool = False
    size: int = 80
    border_radius: int = 50
    border_color: str = "#e5e7eb"
    border_width: int = 0
    shadow_width: int = 0
    aspect_ratio: float = 1.0
    rotation: float = 0.0

class ExperienceItem(BaseModel):
    id: str = ""
    hidden: bool = False
    company: str = ""
    position: str = ""      # canonical name (alias: title)
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    url: str = ""
    bullet_points: list[str] = Field(default_factory=list)

class EducationItem(BaseModel):
    id: str = ""
    hidden: bool = False
    institution: str = ""
    degree: str = ""
    field: str = ""
    grade: str = ""         # canonical name (alias: cgpa_or_percentage)
    location: str = ""
    graduation_date: str = ""
    description: str = ""

class ProjectItem(BaseModel):
    id: str = ""
    hidden: bool = False
    name: str = ""
    period: str = ""        # canonical name (alias: date)
    url: str = ""           # canonical name (alias: link)
    technologies: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)

class SkillItem(BaseModel):
    id: str = ""
    hidden: bool = False
    name: str = ""
    level: int = 0          # 0–5
    keywords: list[str] = Field(default_factory=list)

class LanguageItem(BaseModel):
    id: str = ""
    hidden: bool = False
    language: str = ""
    fluency: str = ""       # e.g. "Native", "Fluent"
    level: int = 0

class AwardItem(BaseModel):
    id: str = ""
    hidden: bool = False
    title: str = ""
    awarder: str = ""
    date: str = ""
    description: str = ""

class CertItem(BaseModel):
    id: str = ""
    hidden: bool = False
    title: str = ""
    issuer: str = ""
    date: str = ""
    url: str = ""
    description: str = ""

class PubItem(BaseModel):
    id: str = ""
    hidden: bool = False
    title: str = ""
    publisher: str = ""
    date: str = ""
    url: str = ""
    summary: str = ""

class VolunteerItem(BaseModel):
    id: str = ""
    hidden: bool = False
    organization: str = ""
    position: str = ""
    location: str = ""
    period: str = ""
    description: str = ""

class InterestItem(BaseModel):
    id: str = ""
    hidden: bool = False
    name: str = ""
    keywords: list[str] = Field(default_factory=list)

class ReferenceItem(BaseModel):
    id: str = ""
    hidden: bool = False
    name: str = ""
    position: str = ""
    phone: str = ""
    url: str = ""
    description: str = ""

class CustomSectionItem(BaseModel):
    id: str = ""
    hidden: bool = False
    title: str = ""
    subtitle: str = ""
    date: str = ""
    bullets: list[str] = Field(default_factory=list)

class CustomSection(BaseModel):
    id: str = ""
    hidden: bool = False
    name: str = ""
    items: list[CustomSectionItem] = Field(default_factory=list)


# ─── Root model ────────────────────────────────────────────────────────────────

DEFAULT_SECTION_ORDER = [
    "summary", "experience", "education", "projects",
    "skills", "languages", "certifications", "awards",
    "publications", "volunteer", "interests", "references", "custom_sections",
]

class ResumeJSON(BaseModel):
    schema_version: int = 1

    contact: Contact = Field(default_factory=Contact)
    photo: Photo = Field(default_factory=Photo)
    summary: str = ""
    profiles: list[ProfileLink] = Field(default_factory=list)

    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    skills: list[SkillItem] = Field(default_factory=list)
    languages: list[LanguageItem] = Field(default_factory=list)
    awards: list[AwardItem] = Field(default_factory=list)
    certifications: list[CertItem] = Field(default_factory=list)
    publications: list[PubItem] = Field(default_factory=list)
    volunteer: list[VolunteerItem] = Field(default_factory=list)
    interests: list[InterestItem] = Field(default_factory=list)
    references: list[ReferenceItem] = Field(default_factory=list)
    custom_sections: list[CustomSection] = Field(default_factory=list)

    # User-controlled ordering and visibility
    section_order: list[str] = Field(default_factory=lambda: list(DEFAULT_SECTION_ORDER))
    section_visibility: dict[str, bool] = Field(default_factory=dict)

    class Config:
        # Allow extra fields from legacy rows to pass through without error
        extra = "allow"
