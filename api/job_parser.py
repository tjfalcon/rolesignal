import re

from api.models import (
    Importance,
    JobRequirement,
    JobSection,
    JobSectionType,
    RequirementCategory,
    RequirementType,
)

SKILLS = [
    "python",
    "fastapi",
    "typescript",
    "javascript",
    "react",
    "react native",
    "next.js",
    "node.js",
    "java",
    "c#",
    "api",
    "sql",
    "postgresql",
    "rag",
    "retrieval",
    "embeddings",
    "vector search",
    "llm",
    "agent",
    "agentic workflows",
    "claude code",
    "cursor",
    "codex",
    "github copilot",
    "observability",
    "testing",
    "pytest",
    "playwright",
    "ci/cd",
    "github actions",
    "vercel",
    "aws",
    "azure",
    "docker",
    "kubernetes",
    "technical leadership",
    "stakeholder management",
    "machine learning",
    "agile",
    "scrum",
]

HEADING_MARKUP = re.compile(r"^(?:#{1,6}\s+|\*\*|__)(.*?)(?:\*\*|__)?\s*$")
BULLET_PREFIX = re.compile(r"^(?:\s*[•*\-–—]\s+|\s*\d+[.)]\s+)")


def normalized_heading(line: str) -> str:
    stripped = line.strip()
    match = HEADING_MARKUP.match(stripped)
    if match:
        stripped = match.group(1)
    return stripped.strip(" *_#:—–-").strip()


def classify_section_heading(heading: str) -> JobSectionType | None:
    value = heading.lower().strip()
    if not value:
        return None
    if any(term in value for term in ("work authorization", "visa", "sponsorship")):
        return JobSectionType.WORK_AUTHORIZATION
    if any(term in value for term in ("equal opportunity", "privacy", "legal")):
        return JobSectionType.LEGAL
    if any(term in value for term in ("what we offer", "benefits", "perks")):
        return JobSectionType.BENEFITS
    if any(term in value for term in ("compensation", "salary", "pay range")):
        return JobSectionType.COMPENSATION
    if any(term in value for term in ("location", "work arrangement", "schedule")):
        return JobSectionType.LOCATION_AND_SCHEDULE
    if any(term in value for term in ("responsibilities", "what you will do", "what you'll do")):
        return JobSectionType.RESPONSIBILITIES
    if any(
        term in value
        for term in (
            "what we're looking for",
            "what we are looking for",
            "qualifications",
            "requirements",
            "who you are",
        )
    ):
        return JobSectionType.QUALIFICATIONS
    if value.startswith("about ") or value in {"about us", "company", "who we are"}:
        return JobSectionType.COMPANY_DESCRIPTION
    if value in {"the position", "the role", "position", "role", "the opportunity"}:
        return JobSectionType.POSITION_SUMMARY
    return None


def parse_sections(job_text: str) -> list[JobSection]:
    pending_heading = "Unlabeled posting content"
    pending_type = JobSectionType.UNKNOWN
    pending_position = 0
    pending_lines: list[str] = []
    sections: list[JobSection] = []

    def flush() -> None:
        nonlocal pending_lines
        text = "\n".join(line for line in pending_lines if line.strip()).strip()
        if not text:
            pending_lines = []
            return
        sections.append(
            JobSection(
                id=f"section-{len(sections) + 1:02d}",
                heading=pending_heading,
                section_type=pending_type,
                source_position=pending_position,
                text=text,
            )
        )
        pending_lines = []

    for position, raw_line in enumerate(job_text.splitlines(), start=1):
        heading = normalized_heading(raw_line)
        section_type = classify_section_heading(heading)
        is_marked_heading = bool(HEADING_MARKUP.match(raw_line.strip()))
        is_bullet = bool(re.match(r"^(?:[-•–—]|\d+[.)])\s+", raw_line.strip()))
        if (
            section_type is not None
            and not is_bullet
            and (is_marked_heading or len(raw_line.strip()) <= 80)
        ):
            flush()
            pending_heading = heading
            pending_type = section_type
            pending_position = position
            continue
        pending_lines.append(raw_line)
    flush()
    return sections


def normalize_skills(text: str) -> list[str]:
    lowered = text.lower().replace("nextjs", "next.js").replace("nodejs", "node.js")
    aliases = {
        "retrieval-augmented generation": "rag",
        "large language model": "llm",
        "apis": "api",
        "copilot": "github copilot",
    }
    for source, target in aliases.items():
        lowered = lowered.replace(source, target)
    return [skill for skill in SKILLS if skill in lowered]


def classify_requirement_type(text: str, skills: list[str]) -> RequirementType:
    lowered = text.lower()
    if any(term in lowered for term in ("authorized to work", "work authorization", "sponsor")):
        return RequirementType.WORK_AUTHORIZATION
    if any(term in lowered for term in ("degree", "bachelor", "master's", "college")):
        return RequirementType.EDUCATION
    if any(term in lowered for term in ("english", "spanish", "bilingual", "language")):
        return RequirementType.LANGUAGE
    if any(term in lowered for term in ("hours per week", "40 hours", "schedule")):
        return RequirementType.SCHEDULE
    if any(term in lowered for term in ("remote", "hybrid", "location", "travel", "based in")):
        return RequirementType.LOCATION
    if any(term in lowered for term in ("salary", "compensation", "pay range")):
        return RequirementType.COMPENSATION
    if re.search(r"\b\d+[–—+\-\d]*\+?\s+years?\b", lowered) or "experience" in lowered:
        return RequirementType.EXPERIENCE
    if any(
        term in lowered
        for term in ("cto", "vp of engineering", "leadership", "technical lead", "architect")
    ):
        return RequirementType.LEADERSHIP
    if skills:
        return RequirementType.TECHNICAL
    if any(term in lowered for term in ("industry", "regulated", "fintech", "healthcare")):
        return RequirementType.DOMAIN
    return RequirementType.RESPONSIBILITY


def classify_category(
    text: str, section_type: JobSectionType, requirement_type: RequirementType
) -> RequirementCategory:
    lowered = text.lower()
    if requirement_type == RequirementType.COMPENSATION:
        return RequirementCategory.COMPENSATION
    if requirement_type in {RequirementType.LOCATION, RequirementType.SCHEDULE}:
        return RequirementCategory.LOCATION
    if any(word in lowered for word in ("preferred", "bonus", "nice to have", "ideally")):
        return RequirementCategory.PREFERRED
    if section_type == JobSectionType.QUALIFICATIONS or any(
        word in lowered for word in ("must", "required", "years of", "proficiency", "expertise")
    ):
        return RequirementCategory.REQUIRED
    if requirement_type == RequirementType.DOMAIN:
        return RequirementCategory.DOMAIN
    return RequirementCategory.RESPONSIBILITY


def is_legal_boilerplate(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "equal opportunity",
            "regardless of race",
            "applicants privacy notice",
            "privacy notice",
        )
    )


def extract_requirements(job_text: str) -> tuple[list[JobSection], list[JobRequirement]]:
    sections = parse_sections(job_text)
    requirements: list[JobRequirement] = []
    seen: set[str] = set()
    excluded_sections = {JobSectionType.COMPANY_DESCRIPTION, JobSectionType.LEGAL}

    for section in sections:
        if section.section_type in excluded_sections:
            continue
        lines = [BULLET_PREFIX.sub("", line).strip() for line in section.text.splitlines()]
        candidates = [line for line in lines if 8 <= len(line) <= 700]
        if len(candidates) < 1 and len(section.text) >= 18:
            candidates = [
                part.strip()
                for part in re.split(r"(?<=[.!?])\s+", section.text)
                if len(part.strip()) >= 18
            ]
        for source_position, text in enumerate(candidates, start=1):
            key = text.lower()
            if key in seen or is_legal_boilerplate(text):
                continue
            skills = normalize_skills(text)
            requirement_type = classify_requirement_type(text, skills)
            if len(text) < 18 and requirement_type not in {
                RequirementType.COMPENSATION,
                RequirementType.LOCATION,
                RequirementType.SCHEDULE,
                RequirementType.WORK_AUTHORIZATION,
            }:
                continue
            if section.section_type == JobSectionType.BENEFITS and requirement_type not in {
                RequirementType.COMPENSATION,
                RequirementType.LOCATION,
                RequirementType.SCHEDULE,
            }:
                continue
            category = classify_category(text, section.section_type, requirement_type)
            high = category == RequirementCategory.REQUIRED or bool(
                re.search(r"\b[5-9]\d*[–—+\-\d]*\+?\s+years?\b", text.lower())
            )
            seen.add(key)
            requirements.append(
                JobRequirement(
                    id=f"req-{len(requirements) + 1:02d}",
                    text=text,
                    category=category,
                    importance=Importance.HIGH if high else Importance.MEDIUM,
                    normalized_skills=skills,
                    requirement_type=requirement_type,
                    section_id=section.id,
                    source_heading=section.heading,
                    source_position=source_position,
                )
            )
            if len(requirements) >= 30:
                return sections, requirements
    return sections, requirements
