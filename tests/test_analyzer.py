from pathlib import Path

from api.analyzer import analyze_job, assess, extract_requirements, load_corpus
from api.job_parser import parse_sections
from api.models import (
    AssessmentStatus,
    CandidateEvidence,
    Importance,
    JobRequirement,
    JobSectionType,
    RequirementCategory,
    RequirementType,
)
from api.retrieval import RankedEvidence


def test_extracts_classifies_and_normalizes_requirements() -> None:
    requirements = extract_requirements(
        "Required: Build retrieval-augmented generation APIs with Python and FastAPI.\n"
        "Kubernetes experience is preferred.\n"
        "The role is remote within the United States."
    )

    assert len(requirements) == 3
    assert requirements[0].category == RequirementCategory.REQUIRED
    assert {"rag", "python", "fastapi", "api"} <= set(requirements[0].normalized_skills)
    assert requirements[1].category == RequirementCategory.PREFERRED
    assert requirements[2].category == RequirementCategory.LOCATION


def test_missing_experience_never_receives_candidate_citation() -> None:
    analysis = analyze_job(
        "Required: Own CUDA kernel optimization for large-scale GPU training clusters.\n"
        "Required: Publish novel deep-learning research at major academic conferences.\n"
        "The position is hybrid in New York City.",
        "demo-thomas",
    )

    missing = [item for item in analysis.assessments if item.status == AssessmentStatus.MISSING]
    assert missing
    assert all(not item.evidence_ids and not item.matches for item in missing)


def test_supported_citations_match_the_requirement_skill() -> None:
    requirement = JobRequirement(
        id="requirement-1",
        text="Build React applications with Kubernetes",
        category=RequirementCategory.REQUIRED,
        importance=Importance.HIGH,
        normalized_skills=["kubernetes"],
    )
    evidence = [
        CandidateEvidence(
            id=f"evidence-{index}",
            claim=claim,
            skill_tags=tags,
            source="Test resume",
            source_locator=f"line {index}",
        )
        for index, claim, tags in [
            (1, "Built React applications for customers", ["react"]),
            (2, "Built applications with React", ["react"]),
            (3, "Managed Kubernetes clusters", ["kubernetes"]),
        ]
    ]

    class RankedBackend:
        def search(self, query: str, profile_id: str, limit: int = 3) -> list[RankedEvidence]:
            return [RankedEvidence(item, 0.9, "test") for item in evidence]

    result = assess(requirement, evidence, RankedBackend(), "demo-thomas")  # type: ignore[arg-type]

    assert result.status == AssessmentStatus.SUPPORTED
    assert result.evidence_ids == ["evidence-3"]


def test_compound_skill_requirement_is_not_supported_by_one_skill() -> None:
    analysis = analyze_job(
        "Required: Build Python and Kubernetes services for fleet operations.",
        "demo-thomas",
    )

    assert analysis.requirements[0].normalized_skills == ["python", "kubernetes"]
    assert analysis.assessments[0].status == AssessmentStatus.ADJACENT
    assert analysis.assessments[0].evidence_ids == ["ghost-python"]


def test_corpus_is_sanitized_and_public() -> None:
    corpus = load_corpus("demo-thomas")
    assert corpus
    assert all(item.visibility == "public" for item in corpus)
    assert all("@" not in item.claim for item in corpus)


def test_section_parser_separates_company_requirements_and_constraints() -> None:
    posting = (Path("tests/fixtures") / "fullstack_principal_agentic.txt").read_text()
    sections = parse_sections(posting)
    requirements = extract_requirements(posting)

    assert [section.section_type for section in sections] == [
        JobSectionType.COMPANY_DESCRIPTION,
        JobSectionType.POSITION_SUMMARY,
        JobSectionType.QUALIFICATIONS,
        JobSectionType.WORK_AUTHORIZATION,
        JobSectionType.BENEFITS,
    ]
    requirement_text = " ".join(item.text for item in requirements).lower()
    assert "net promoter score" not in requirement_text
    assert "life-changing career opportunities" not in requirement_text
    assert "health, dental" not in requirement_text
    assert "equal opportunity" not in requirement_text
    assert "claude code" in requirement_text
    assert "currently authorized to work" in requirement_text
    assert "100% remote work" in requirement_text
    assert all(item.section_id and item.source_heading for item in requirements)


def test_short_requirement_sentence_is_not_mistaken_for_a_section_heading() -> None:
    posting = (
        "Requirements\n"
        "Build privacy-aware applications and maintain audit trails.\n"
        "Experience with Python services."
    )

    sections = parse_sections(posting)
    requirements = extract_requirements(posting)

    assert len(sections) == 1
    assert sections[0].section_type == JobSectionType.QUALIFICATIONS
    assert [item.text for item in requirements] == [
        "Build privacy-aware applications and maintain audit trails.",
        "Experience with Python services.",
    ]


def test_candidate_constraints_require_confirmation_not_resume_similarity() -> None:
    posting = (Path("tests/fixtures") / "fullstack_principal_agentic.txt").read_text()
    analysis = analyze_job(posting, "demo-thomas")
    requirement_by_id = {item.id: item for item in analysis.requirements}

    constraints = [
        assessment
        for assessment in analysis.assessments
        if requirement_by_id[assessment.requirement_id].requirement_type
        in {
            RequirementType.EDUCATION,
            RequirementType.LANGUAGE,
            RequirementType.LOCATION,
            RequirementType.SCHEDULE,
            RequirementType.WORK_AUTHORIZATION,
        }
    ]
    assert constraints
    assert all(item.status == AssessmentStatus.UNKNOWN for item in constraints)
    assert all(not item.evidence_ids for item in constraints)
