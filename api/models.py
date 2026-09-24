from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RequirementCategory(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    RESPONSIBILITY = "responsibility"
    DOMAIN = "domain"
    COMPENSATION = "compensation"
    LOCATION = "location"


class Importance(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AssessmentStatus(StrEnum):
    SUPPORTED = "supported"
    ADJACENT = "adjacent"
    MISSING = "missing"
    UNKNOWN = "unknown"


class JobSectionType(StrEnum):
    COMPANY_DESCRIPTION = "company_description"
    POSITION_SUMMARY = "position_summary"
    RESPONSIBILITIES = "responsibilities"
    QUALIFICATIONS = "qualifications"
    WORK_AUTHORIZATION = "work_authorization"
    LOCATION_AND_SCHEDULE = "location_and_schedule"
    COMPENSATION = "compensation"
    BENEFITS = "benefits"
    LEGAL = "legal"
    UNKNOWN = "unknown"


class RequirementType(StrEnum):
    TECHNICAL = "technical"
    EXPERIENCE = "experience"
    LEADERSHIP = "leadership"
    EDUCATION = "education"
    LANGUAGE = "language"
    WORK_AUTHORIZATION = "work_authorization"
    LOCATION = "location"
    SCHEDULE = "schedule"
    COMPENSATION = "compensation"
    RESPONSIBILITY = "responsibility"
    DOMAIN = "domain"
    GENERAL = "general"


class CandidateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    claim: str
    skill_tags: list[str]
    source: str
    source_locator: str
    visibility: str = "public"


class ResumeVersionSummary(BaseModel):
    id: str
    version_number: int
    label: str
    status: str
    source_name: str
    evidence_count: int = 0
    created_at: datetime
    activated_at: datetime | None = None


class CandidateProfileDetail(BaseModel):
    id: str
    display_name: str
    headline: str
    visibility: str
    active_resume_version_id: str | None
    versions: list[ResumeVersionSummary]


class ResumeVersionCreate(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    source_name: str = Field(default="Manual entry", min_length=1, max_length=255)
    copy_active_evidence: bool = True


class EvidenceCreate(BaseModel):
    claim: str = Field(min_length=10, max_length=2_000)
    skill_tags: list[str] = Field(min_length=1, max_length=30)
    source: str = Field(min_length=1, max_length=255)
    source_locator: str = Field(min_length=1, max_length=500)
    visibility: str = Field(default="public", pattern="^(public|private)$")


class EvidenceUpdate(BaseModel):
    claim: str | None = Field(default=None, min_length=10, max_length=2_000)
    skill_tags: list[str] | None = Field(default=None, min_length=1, max_length=30)
    source: str | None = Field(default=None, min_length=1, max_length=255)
    source_locator: str | None = Field(default=None, min_length=1, max_length=500)
    visibility: str | None = Field(default=None, pattern="^(public|private)$")
    approved: bool | None = None


class ManagedEvidence(CandidateEvidence):
    approved: bool


class ResumeVersionDetail(ResumeVersionSummary):
    profile_id: str
    evidence: list[ManagedEvidence]


class JobSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    heading: str
    section_type: JobSectionType
    source_position: int = Field(ge=0)
    text: str


class JobRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    category: RequirementCategory
    importance: Importance
    normalized_skills: list[str]
    requirement_type: RequirementType = RequirementType.GENERAL
    section_id: str = "section-01"
    source_heading: str = "Unlabeled posting content"
    source_position: int = Field(default=0, ge=0)


class EvidenceMatch(BaseModel):
    evidence_id: str
    score: float = Field(ge=0, le=1)
    retrieval_method: str


class RequirementAssessment(BaseModel):
    requirement_id: str
    status: AssessmentStatus
    evidence_ids: list[str]
    explanation: str
    confidence: float = Field(ge=0, le=1)
    matches: list[EvidenceMatch] = Field(default_factory=list)


class AnalysisMetrics(BaseModel):
    mode: str
    latency_ms: int
    estimated_cost_usd: float
    evidence_coverage: float = Field(ge=0, le=1)


class AnalyzeRequest(BaseModel):
    job_text: str = Field(min_length=80, max_length=30_000)
    candidate_profile_id: str = Field(
        default="demo-thomas", pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80
    )


class FitAnalysis(BaseModel):
    analysis_id: str
    sections: list[JobSection]
    requirements: list[JobRequirement]
    assessments: list[RequirementAssessment]
    primary_strengths: list[str]
    ranked_gaps: list[str]
    interview_prompts: list[str]
    limitations: list[str]
    evidence: list[CandidateEvidence]
    metrics: AnalysisMetrics


class HealthResponse(BaseModel):
    status: str
    mode: str
    database: str
    model_provider: str
