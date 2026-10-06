import pytest

from api.job_parser import normalize_skills
from api.models import EvidenceCreate, EvidenceUpdate
from api.profile_service import ProfileService
from api.skills import detect_skills


@pytest.mark.parametrize(("text", "expected"), [
    ("Integrated Vercel + Sitecore + nextjs.", ["next.js", "vercel", "sitecore"]),
    ("Prepared a Next.js app for deployment on Azure.", ["next.js", "azure"]),
    ("JavaScript and PostgreSQL", ["javascript", "postgresql"]),
    ("C++, C#, APIs, NodeJS, Next JS", ["next.js", "node.js", "c#", "api", "c++"]),
    ("Scrumptious reactive fragments", []),
    ("Next.js nextjs NEXT JS", ["next.js"]),
    ("Worked with a team to improve the onboarding process.", []),
])
def test_literal_mentions(text, expected):
    assert detect_skills(text) == expected
    assert normalize_skills(text) == expected


def test_capture_requires_only_text():
    payload = EvidenceCreate(claim="Improved the onboarding process.")
    assert payload.source == "Manual entry"
    assert payload.source_locator == ""
    assert payload.skill_tags is None
    assert EvidenceCreate(claim=payload.claim, skill_tags=[]).skill_tags == []
    assert ProfileService._normalize_tags([]) == []
    assert EvidenceUpdate(source_locator="", skill_tags=[]).skill_tags == []
