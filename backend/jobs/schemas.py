from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class SearchPreferences(BaseModel):
    target_roles: list[str] = Field(default_factory=lambda: ["Software Engineer", "Backend Developer"], min_length=1, max_length=8)
    locations: list[str] = Field(default_factory=lambda: ["India"], max_length=12)
    work_modes: list[Literal["remote", "hybrid", "onsite"]] = Field(default_factory=lambda: ["remote", "hybrid", "onsite"], min_length=1)
    employment_types: list[Literal["full_time", "internship", "contract", "part_time"]] = Field(default_factory=lambda: ["full_time"], min_length=1)
    graduation_year: int | None = Field(default=None, ge=2000, le=2040)
    education_status: Literal["student", "graduate", "unspecified"] = "unspecified"
    institution: str = Field(default="", max_length=200)
    earliest_joining_date: date | None = None
    max_required_experience: float = Field(default=0, ge=0, le=10)
    minimum_salary_annual_inr: int | None = Field(default=None, ge=0, le=100000000)
    degree: str = Field(default="", max_length=150)
    course: str = Field(default="", max_length=150)
    excluded_companies: list[str] = Field(default_factory=list, max_length=30)
    country_code: str = Field(default="in", pattern=r"^[a-z]{2}$")
    max_posting_age_days: int | None = Field(default=60, ge=1, le=365)

    @field_validator("target_roles", "locations", "excluded_companies")
    @classmethod
    def clean_lists(cls, items):
        values = list(dict.fromkeys(value.strip() for value in items if value.strip()))
        if any(len(value) > 150 for value in values):
            raise ValueError("Each preference must be 150 characters or fewer.")
        return values

    @model_validator(mode="after")
    def require_roles(self):
        if not self.target_roles:
            raise ValueError("Choose at least one target role.")
        return self


class SourceInput(BaseModel):
    provider: str = Field(min_length=1, max_length=20)
    board: str = Field(min_length=1, max_length=300)
    company: str = Field(min_length=1, max_length=150)
    enabled: bool = True

    @field_validator("provider")
    @classmethod
    def registered_provider(cls, value):
        from jobs.adapters import ADAPTERS
        if value not in {*ADAPTERS, "auto", "adzuna"}:
            raise ValueError("Choose a registered adapter or use reviewed import for this platform.")
        return value

    @field_validator("board", "company")
    @classmethod
    def nonempty(cls, value):
        value = value.strip()
        if not value: raise ValueError("This field cannot be empty.")
        return value


class FeedInput(BaseModel):
    company: str = Field(min_length=1, max_length=150)
    feed_url: str = Field(min_length=8, max_length=2000)
    format: Literal["auto", "xml", "json", "jsonld"] = "auto"
    full_descriptions: bool = False
    enabled: bool = True

    @field_validator("company")
    @classmethod
    def company_name(cls, value):
        if not value.strip(): raise ValueError("Supply the employer or source name.")
        return value.strip()

    @field_validator("feed_url")
    @classmethod
    def public_feed(cls, value):
        from jobs.feed_transport import feed_url
        return feed_url(value.strip())


class EmployerConnectionInput(BaseModel):
    provider: Literal["workday", "taleo", "sap_successfactors", "oracle_recruiting", "icims"]
    company: str = Field(min_length=1, max_length=150)
    url: str = Field(min_length=8, max_length=2000)
    access_reviewed: bool = False
    full_descriptions: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def reviewed(self):
        if not self.company.strip(): raise ValueError("Supply an employer name.")
        if not self.access_reviewed: raise ValueError("Confirm this employer publishes the URL for public collection before connecting.")
        from jobs.enterprise import configuration
        configuration(self.provider, self.url, self.full_descriptions)
        return self


class ExportPreviewInput(BaseModel):
    content: str = Field(min_length=1, max_length=2000000)
    format: Literal["csv", "json"] = "csv"


class ExportImportInput(ExportPreviewInput):
    rows: list[int] = Field(min_length=1, max_length=100)
    confirmed: bool = False
    full_descriptions: bool = False


class ManualJob(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    company: str = Field(min_length=1, max_length=150)
    location: str = Field(default="", max_length=250)
    apply_url: str = Field(max_length=2000)
    description: str = Field(min_length=50, max_length=100000)
    description_complete: bool = True

    @field_validator("title", "company", "description")
    @classmethod
    def nonempty(cls, value):
        value = value.strip()
        if not value: raise ValueError("This field cannot be empty.")
        return value
