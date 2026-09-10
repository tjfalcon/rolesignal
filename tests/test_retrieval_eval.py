import json
from pathlib import Path

from api.analyzer import load_corpus
from api.retrieval import hybrid_search


def test_golden_retrieval_recall_at_five_is_at_least_eighty_percent() -> None:
    cases = json.loads((Path("evals") / "golden.json").read_text())
    corpus = load_corpus("demo-thomas")
    hits = 0

    for case in cases:
        retrieved = {item.evidence.id for item in hybrid_search(case["query"], corpus, limit=5)}
        hits += case["evidence"] in retrieved

    recall_at_five = hits / len(cases)
    assert len(cases) >= 30
    assert recall_at_five >= 0.8, f"recall@5={recall_at_five:.3f}"
