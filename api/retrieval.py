import hashlib
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from api.models import CandidateEvidence, EvidenceMatch

TOKEN_RE = re.compile(r"[a-z0-9+#.]+")
SYNONYMS = {
    "javascript": {"typescript", "node.js", "react", "next.js"},
    "backend": {"node.js", "api", "fastapi", "python"},
    "frontend": {"react", "next.js", "typescript"},
    "leadership": {"technical leadership", "mentoring", "stakeholder management"},
    "rag": {"retrieval", "embeddings", "vector search"},
    "llm": {"ai", "agent", "rag", "prompt engineering"},
    "devops": {"ci/cd", "github actions", "vercel", "delivery"},
}


def tokenize(text: str) -> list[str]:
    tokens = TOKEN_RE.findall(
        text.lower().replace("nextjs", "next.js").replace("nodejs", "node.js")
    )
    expanded = list(tokens)
    for token in tokens:
        expanded.extend(SYNONYMS.get(token, set()))
    return expanded


def lexical_score(query: str, evidence: CandidateEvidence) -> float:
    query_terms = set(tokenize(query))
    doc_terms = set(tokenize(f"{evidence.claim} {' '.join(evidence.skill_tags)}"))
    if not query_terms:
        return 0.0
    overlap = sum(2 if term in evidence.skill_tags else 1 for term in query_terms & doc_terms)
    return min(1.0, overlap / max(4, len(query_terms) * 0.6))


def local_embedding(text: str, dimensions: int = 192) -> list[float]:
    vector = [0.0] * dimensions
    counts = Counter(tokenize(text))
    for token, count in counts.items():
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1 if digest[4] % 2 == 0 else -1
        vector[index] += sign * (1 + math.log(count))
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    return max(0.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=True))))


@dataclass(frozen=True)
class RankedEvidence:
    evidence: CandidateEvidence
    score: float
    method: str


def hybrid_search(
    query: str, corpus: list[CandidateEvidence], limit: int = 3
) -> list[RankedEvidence]:
    query_vector = local_embedding(query)
    lexical = sorted(corpus, key=lambda item: lexical_score(query, item), reverse=True)
    vector = sorted(
        corpus,
        key=lambda item: cosine(
            query_vector, local_embedding(f"{item.claim} {' '.join(item.skill_tags)}")
        ),
        reverse=True,
    )
    scores: dict[str, float] = defaultdict(float)
    for rank, item in enumerate(lexical, start=1):
        scores[item.id] += 1 / (60 + rank)
    for rank, item in enumerate(vector, start=1):
        scores[item.id] += 1 / (60 + rank)
    by_id = {item.id: item for item in corpus}
    max_rrf = 2 / 61
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [
        RankedEvidence(by_id[item_id], round(score / max_rrf, 4), "hybrid-local-rrf")
        for item_id, score in ranked
    ]


def to_match(item: RankedEvidence) -> EvidenceMatch:
    return EvidenceMatch(
        evidence_id=item.evidence.id,
        score=item.score,
        retrieval_method=item.method,
    )
