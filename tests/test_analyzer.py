from pathlib import Path

from api.analyzer import analyze_job, extract_requirements, load_corpus
from api.job_parser import parse_sections
from api.models import (
    AssessmentStatus,
    JobSectionType,
    RequirementCategory,
    RequirementType,
)


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
