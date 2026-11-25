from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.analyzer import analyze_job
from api.job_parser import extract_requirements, parse_sections
from api.main import app
from api.models import AssessmentStatus, JobSectionType, RequirementCategory, RequirementType
from api.retrieval_backends import LocalRetrievalBackend

POSTING = (Path(__file__).parent / "fixtures" / "copied_job_board.txt").read_text()
BENEFIT_SUMMARY = (
    "401(k) 4% Match, 401(k), Health insurance, Paid time off, Vision insurance, "
    "Health savings account, Dental insurance, Flexible spending account"
)


def test_copied_posting_separates_context_duties_and_footer_qualifications() -> None:
    sections, requirements = extract_requirements(POSTING)
    by_text = {item.text: item for item in requirements}
    assert sections[0].section_type == JobSectionType.POSTING_METADATA
    assert BENEFIT_SUMMARY not in by_text
    assert not any(
        item.text.startswith(
            (
                "Staff Software Engineer",
                "We're Example Systems",
                "Our culture",
                "Our company",
                "Show 5 more",
            )
        )
        for item in requirements
    )
    duty = by_text["Build TypeScript and React applications for clients."]
    assert duty.category == RequirementCategory.RESPONSIBILITY
    assert duty.source_heading == "What You’ll Do"
    assert by_text["You have familiarity with Kubernetes and Terraform."].category == (
        RequirementCategory.REQUIRED
    )
    footer = by_text["Software Engineer: 5 years (Required)"]
    assert footer.category == RequirementCategory.REQUIRED
    assert footer.source_heading == "Experience"
    assert "Build employee benefits APIs using Python and FastAPI." in by_text
    assert all(item.text in POSTING for item in requirements)


@pytest.mark.parametrize(
    "heading",
    ["What you'll do:", "What You’ll Do:", "\u200dWhat You’ll Do:", "**What You’ll Do:**"],
)
def test_responsibility_headings_accept_copy_paste_typography(heading: str) -> None:
    sections, requirements = extract_requirements(f"{heading}\nBuild Python services for clients.")
    assert len(sections) == 1
    assert sections[0].section_type == JobSectionType.RESPONSIBILITIES
    assert requirements[0].text == "Build Python services for clients."


@pytest.mark.parametrize(
    "benefit", [BENEFIT_SUMMARY, "Health insurance", "401(k)", "Paid time off; Dental insurance"]
)
def test_unheaded_benefits_do_not_become_requirements_or_swallow_work(benefit: str) -> None:
    _, requirements = extract_requirements(
        f"Required: Build Python services for clients.\n{benefit}\n"
        "Required: Operate production Kubernetes clusters."
    )
    assert [item.text for item in requirements] == [
        "Required: Build Python services for clients.",
        "Required: Operate production Kubernetes clusters.",
    ]


def test_benefits_and_schedule_words_in_real_work_do_not_start_sections() -> None:
    work = "Build benefits APIs and schedule background jobs using Python"
    sections, requirements = extract_requirements(f"Responsibilities\n{work}")
    assert len(sections) == 1
    assert sections[0].section_type == JobSectionType.RESPONSIBILITIES
    assert requirements[0].text == work


def test_job_details_without_a_board_wrapper_retains_candidate_work() -> None:
    _, requirements = extract_requirements("Job details\nBuild Python services for clients.")
    assert [item.text for item in requirements] == ["Build Python services for clients."]


def test_company_noise_does_not_fill_the_requirement_limit() -> None:
    noise = "\n".join(f"Our company runs social event number {index}." for index in range(40))
    posting = POSTING.replace("Our culture includes outdoor activities and team events.", noise)
    _, requirements = extract_requirements(posting)
    assert len(requirements) < 30
    assert any(item.text == "Software Engineer: 5 years (Required)" for item in requirements)
    assert not any("social event" in item.text for item in requirements)


@pytest.mark.parametrize(
    "wage",
    ["$160,000 - $240,000 a year", "$85 per hour", "Pay: $160,000.00 - $240,000.00 per year"],
)
def test_wages_require_confirmation_and_never_get_career_citations(wage: str) -> None:
    analysis = analyze_job(
        f"Required: Build TypeScript applications for clients.\n{wage}",
        "demo-thomas",
        backend=LocalRetrievalBackend(),
    )
    requirement = next(item for item in analysis.requirements if item.text == wage)
    assessment = next(
        item for item in analysis.assessments if item.requirement_id == requirement.id
    )
    assert requirement.requirement_type == RequirementType.COMPENSATION
    assert assessment.status == AssessmentStatus.UNKNOWN
    assert not assessment.evidence_ids


def test_api_excludes_benefits_and_preserves_actual_duties_and_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("api.main.RETRIEVAL_BACKEND", LocalRetrievalBackend())
    response = TestClient(app).post("/v1/analyze", json={"job_text": POSTING})
    assert response.status_code == 200
    data = response.json()
    requirements = {item["text"]: item for item in data["requirements"]}
    assert BENEFIT_SUMMARY not in requirements
    assert not any(BENEFIT_SUMMARY in gap for gap in data["ranked_gaps"])
    assert requirements["Build TypeScript and React applications for clients."]["category"] == (
        "responsibility"
    )
    assert requirements["Software Engineer: 5 years (Required)"]["category"] == "required"
    constraints = {
        item["id"]
        for item in data["requirements"]
        if item["requirement_type"] in {"compensation", "location", "schedule"}
    }
    assert constraints
    assert all(
        item["status"] == "unknown" and not item["evidence_ids"]
        for item in data["assessments"]
        if item["requirement_id"] in constraints
    )
    assert any(item["text"] == "Flexible schedule" for item in data["requirements"])


def test_plain_benefit_lines_remain_content_inside_benefits_section() -> None:
    sections = parse_sections("Benefits\nFlexible schedule\nHealth insurance\nCommuter benefits")
    assert len(sections) == 1
    assert sections[0].section_type == JobSectionType.BENEFITS
