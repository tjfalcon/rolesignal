"""Literal skill mentions, not inference of proficiency or hands-on use."""

import json
import re
from pathlib import Path

SKILL_DICTIONARY: dict[str, list[str]] = json.loads(
    Path(__file__).with_name("skill_dictionary.json").read_text()
)
PATTERNS = {
    skill: re.compile(
        r"(?<![a-z0-9_+#])(?:" + "|".join(re.escape(term) for term in [skill, *aliases])
        + r")(?![a-z0-9_+#])", re.IGNORECASE
    )
    for skill, aliases in SKILL_DICTIONARY.items()
}


def detect_skills(text: str) -> list[str]:
    return [skill for skill, pattern in PATTERNS.items() if pattern.search(text)]
