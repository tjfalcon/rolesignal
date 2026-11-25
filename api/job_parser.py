import re
import unicodedata

from api.models import (
    Importance,
    JobRequirement,
    JobSection,
    JobSectionType,
    RequirementCategory,
    RequirementType,
)
from api.skills import detect_skills

HEADING_MARKUP = re.compile(r"^(?:#{1,6}\s+|\*\*|__)(.*?)(?:\*\*|__)?\s*$")
BULLET_PREFIX = re.compile(r"^(?:\s*[•*\-–—]\s+|\s*\d+[.)]\s+)")
BENEFIT_ITEM = re.compile(
    r"(?:401\s*\(k\)(?:\s+(?:\d+(?:\.\d+)?%\s+)?(?:employer\s+)?(?:match|plan))*"
    r"|(?:health|medical|dental|vision|life|disability) insurance"
    r"|(?:health savings|flexible spending) account(?:\s*\((?:HSA|FSA)\))?"
    r"|paid time off|PTO)",
    re.IGNORECASE,
)
WAGE_AMOUNT = re.compile(
    r"[$€£]\s*\d[\d,.]*(?:\s*[-–—]\s*[$€£]?\s*\d[\d,.]*)?\s*"
    r"(?:(?:a|an|per|/)\s*(?:year|yr|hour|hr|month)|annually)\b",
    re.IGNORECASE,
)
CONSTRAINT_TYPES = {
    RequirementType.COMPENSATION,
    RequirementType.LOCATION,
    RequirementType.SCHEDULE,
    RequirementType.WORK_AUTHORIZATION,
}


def normalized_heading(line: str) -> str:
    # Compare headings without invisible copy/paste formatting; source body text
    # remains untouched so requirement quotes still resolve to the posting.
    stripped = "".join(char for char in line if unicodedata.category(char) != "Cf").strip()
    match = HEADING_MARKUP.match(stripped)
    if match:
        stripped = match.group(1)
    return stripped.strip(" *_#:—–-").strip()


def classify_section_heading(heading: str) -> JobSectionType | None:
    value = heading.lower().replace("’", "'").rstrip(":?").strip()
    aliases = {
        JobSectionType.UNKNOWN: {"full job description"},
        JobSectionType.WORK_AUTHORIZATION: {
            "work authorization",
            "work authorization requirements",
            "visa requirements",
            "visa or authorization requirements",
            "sponsorship",
            "sponsorship requirements",
        },
        JobSectionType.LEGAL: {
            "equal opportunity",
            "equal opportunity employer",
            "privacy",
            "privacy notice",
            "privacy policy",
            "legal",
        },
        JobSectionType.BENEFITS: {
            "what we offer",
            "benefits",
            "company benefits",
            "other benefits",
            "employee benefits",
            "compensation and benefits",
            "salary and benefits",
            "pay and benefits",
            "perks",
        },
        JobSectionType.COMPENSATION: {"compensation", "salary", "pay range"},
        JobSectionType.LOCATION_AND_SCHEDULE: {
            "location",
            "work arrangement",
            "schedule",
            "location and schedule",
            "work location",
            "work schedule",
        },
        JobSectionType.RESPONSIBILITIES: {
            "responsibilities",
            "key responsibilities",
            "your responsibilities",
            "job responsibilities",
            "what you will do",
            "what you'll do",
        },
        JobSectionType.QUALIFICATIONS: {
            "what we're looking for",
            "what we are looking for",
            "qualifications",
            "required qualifications",
            "preferred qualifications",
            "minimum qualifications",
            "basic qualifications",
            "technical qualifications",
            "minimum requirements",
            "requirements",
            "who you are",
            "who should apply",
            "you'll fit right in if",
            "this is probably a great fit if",
            "experience",
        },
        JobSectionType.POSITION_SUMMARY: {
            "job details",
            "the position",
            "the role",
            "position",
            "role",
            "the opportunity",
            "about the role",
            "about the job",
        },
    }
    for section_type, headings in aliases.items():
        if value in headings:
            return section_type
    if value.startswith(("about ", "why ")) or value in {"company", "who we are"}:
        return JobSectionType.COMPANY_DESCRIPTION
    return None


def has_job_board_summary(job_text: str) -> bool:
    headings = {normalized_heading(line).lower() for line in job_text.splitlines()}
    return "job details" in headings and "full job description" in headings


def is_benefit_listing(text: str) -> bool:
    return all(BENEFIT_ITEM.fullmatch(part.strip()) for part in re.split(r"[,;]", text))


def parse_sections(job_text: str) -> list[JobSection]:
    pending_heading = "Unlabeled posting content"
    pending_type = JobSectionType.UNKNOWN
    board_summary = has_job_board_summary(job_text)
    if board_summary:
        pending_type = JobSectionType.POSTING_METADATA
    pending_position = 0
    pending_lines: list[str] = []
    sections: list[JobSection] = []
    implicit_company_intro = False

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
        if board_summary and heading.lower() == "job details":
            section_type = JobSectionType.POSTING_METADATA
        is_marked_heading = bool(HEADING_MARKUP.match(raw_line.strip()))
        is_bullet = bool(BULLET_PREFIX.match(raw_line))
        is_sentence = bool(re.search(r"[.!]$", heading))
        if (
            section_type is not None
            and not is_bullet
            and (is_marked_heading or (len(raw_line.strip()) <= 80 and not is_sentence))
        ):
            flush()
            pending_heading = heading
            pending_type = section_type
            pending_position = position
            implicit_company_intro = False
            continue
        # Unheaded employer introductions are common in copied job-board text.
        # Keep the introduction as context, then resume candidate expectations
        # when the text explicitly addresses "you" or "your".
        content_type = None
        if re.match(r"^(?:We're|We’re|We are) [A-Z][\w&-]*(?: [A-Z][\w&-]*){0,4}[.!]", heading):
            content_type = JobSectionType.COMPANY_DESCRIPTION
            implicit_company_intro = True
        elif implicit_company_intro and re.match(r"^(?:you\b|you['’]|your\b)", heading, re.I):
            content_type = JobSectionType.QUALIFICATIONS
            implicit_company_intro = False
        if content_type is not None:
            flush()
            pending_type = content_type
            pending_heading = (
                "Company introduction" if implicit_company_intro else "Candidate expectations"
            )
            pending_position = position
        pending_lines.append(raw_line)
    flush()
    return sections


def normalize_skills(text: str) -> list[str]:
    return detect_skills(text)


def classify_requirement_type(text: str, skills: list[str]) -> RequirementType:
    lowered = text.lower()
    if WAGE_AMOUNT.search(text) or re.match(r"pay\s*:", lowered):
        return RequirementType.COMPENSATION
    if any(term in lowered for term in ("authorized to work", "work authorization", "sponsor")):
        return RequirementType.WORK_AUTHORIZATION
    if any(term in lowered for term in ("degree", "bachelor", "master's", "college")):
        return RequirementType.EDUCATION
    if any(term in lowered for term in ("english", "spanish", "bilingual", "language")):
        return RequirementType.LANGUAGE
    if any(term in lowered for term in ("hours per week", "40 hours", "schedule")) or re.fullmatch(
        r"(?:job type:\s*)?(?:full-time|part-time|contract|temporary|internship)", lowered
    ):
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
    posting_title = next((line.strip() for line in job_text.splitlines() if line.strip()), "")
    board_summary = has_job_board_summary(job_text)

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
            if is_benefit_listing(text):
                continue
            if (
                board_summary
                and section.section_type == JobSectionType.UNKNOWN
                and (text.startswith(posting_title))
            ):
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
            if (
                section.section_type
                in {
                    JobSectionType.BENEFITS,
                    JobSectionType.POSTING_METADATA,
                }
                and requirement_type not in CONSTRAINT_TYPES
            ):
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
