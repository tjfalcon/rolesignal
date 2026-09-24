import json
import time
import uuid
from pathlib import Path

from api.job_parser import extract_requirements as parse_job_requirements
from api.models import (
    AnalysisMetrics,
    AssessmentStatus,
    CandidateEvidence,
    FitAnalysis,
    JobRequirement,
    RequirementAssessment,
    RequirementType,
)
from api.retrieval import lexical_score, to_match
from api.retrieval_backends import (
    FallbackRetrievalBackend,
    LocalRetrievalBackend,
    RetrievalBackend,
)

DATA_DIR = Path(__file__).parent / "data"


def load_fixture_corpus(profile_id: str) -> list[CandidateEvidence]:
    filename = {"demo-thomas": "demo_thomas.json", "synthetic": "synthetic.json"}.get(profile_id)
    if filename is None:
        return []
    raw = json.loads((DATA_DIR / filename).read_text())
    return [CandidateEvidence.model_validate(item) for item in raw]


def load_corpus(profile_id: str) -> list[CandidateEvidence]:
    """Compatibility helper for tests and offline evaluation."""
    return load_fixture_corpus(profile_id)


def extract_requirements(job_text: str) -> list[JobRequirement]:
    return parse_job_requirements(job_text)[1]


def assess(
    requirement: JobRequirement,
    corpus: list[CandidateEvidence],
    backend: RetrievalBackend,
    profile_id: str,
) -> RequirementAssessment:
    if requirement.requirement_type in {
        RequirementType.COMPENSATION,
        RequirementType.EDUCATION,
        RequirementType.LANGUAGE,
        RequirementType.LOCATION,
        RequirementType.SCHEDULE,
        RequirementType.WORK_AUTHORIZATION,
    }:
        return RequirementAssessment(
            requirement_id=requirement.id,
            status=AssessmentStatus.UNKNOWN,
            evidence_ids=[],
            explanation=(
                "This constraint requires current candidate confirmation; "
                "it is not inferred from technical evidence."
            ),
            confidence=0.95,
        )
    ranked = backend.search(requirement.text, profile_id)
    direct = [item for item in ranked if lexical_score(requirement.text, item.evidence) >= 0.24]
    requirement_skills = set(requirement.normalized_skills)
    direct_skill_matches = [
        item for item in ranked if requirement_skills & set(item.evidence.skill_tags)
    ]
    if direct and (not requirement_skills or direct_skill_matches):
        selected = direct[:2]
        status = AssessmentStatus.SUPPORTED
        explanation = (
            "Direct evidence supports this requirement. "
            "Review the cited source before using the claim."
        )
        confidence = 0.88
    elif direct_skill_matches:
        selected = direct_skill_matches[:2]
        status = AssessmentStatus.ADJACENT
        explanation = (
            "Related evidence exists, but it does not prove the complete requirement. "
            "Present it as transferable experience."
        )
        confidence = 0.72
    else:
        selected = []
        status = AssessmentStatus.MISSING
        explanation = (
            "No sufficient evidence was found. Do not convert this gap into a resume claim."
        )
        confidence = 0.9
    return RequirementAssessment(
        requirement_id=requirement.id,
        status=status,
        evidence_ids=[item.evidence.id for item in selected],
        explanation=explanation,
        confidence=confidence,
        matches=[to_match(item) for item in selected],
    )


def analyze_job(
    job_text: str,
    profile_id: str,
    mode: str | None = None,
    backend: RetrievalBackend | None = None,
) -> FitAnalysis:
    started = time.perf_counter()
    active_backend = backend or LocalRetrievalBackend()
    if isinstance(active_backend, FallbackRetrievalBackend):
        active_backend = active_backend.prepare(profile_id)
    corpus = active_backend.load_corpus(profile_id)
    sections, requirements = parse_job_requirements(job_text)
    assessments = [
        assess(requirement, corpus, active_backend, profile_id) for requirement in requirements
    ]
    requirement_by_id = {item.id: item for item in requirements}
    strengths = [
        requirement_by_id[item.requirement_id].text
        for item in assessments
        if item.status == AssessmentStatus.SUPPORTED
    ][:4]
    gaps = [
        requirement_by_id[item.requirement_id].text
        for item in assessments
        if item.status in {AssessmentStatus.MISSING, AssessmentStatus.UNKNOWN}
    ][:5]
    prompts = [
        "What is your strongest concrete example for: "
        f"{requirement_by_id[item.requirement_id].text}?"
        for item in assessments
        if item.status in {AssessmentStatus.SUPPORTED, AssessmentStatus.ADJACENT}
    ][:4]
    covered = sum(
        item.status in {AssessmentStatus.SUPPORTED, AssessmentStatus.ADJACENT}
        for item in assessments
    )
    latency = round((time.perf_counter() - started) * 1000)
    return FitAnalysis(
        analysis_id=str(uuid.uuid4()),
        sections=sections,
        requirements=requirements,
        assessments=assessments,
        primary_strengths=strengths,
        ranked_gaps=gaps,
        interview_prompts=prompts,
        limitations=[
            "This is an evidence comparison, not a hiring prediction.",
            "Deterministic demo mode uses local hybrid retrieval; it does not call a hosted model.",
            "Compensation, location, work authorization, and current preferences "
            "require human confirmation.",
        ],
        evidence=corpus,
        metrics=AnalysisMetrics(
            mode=mode or active_backend.mode,
            latency_ms=latency,
            estimated_cost_usd=0,
            evidence_coverage=round(covered / len(assessments), 3) if assessments else 0,
        ),
    )
