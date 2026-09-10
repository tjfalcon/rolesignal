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


class CandidateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    claim: str
    skill_tags: list[str]
    source: str
    source_locator: str
    visibility: str = "public"


class JobRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    category: RequirementCategory
    importance: Importance
    normalized_skills: list[str]


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
    candidate_profile_id: str = Field(default="demo-thomas", pattern="^(demo-thomas|synthetic)$")


class FitAnalysis(BaseModel):
    analysis_id: str
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
