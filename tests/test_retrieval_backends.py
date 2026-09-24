from api.analyzer import load_fixture_corpus
from api.retrieval import reciprocal_rank_fusion


def test_reciprocal_rank_fusion_combines_rankings_without_raw_score_assumptions() -> None:
    corpus = load_fixture_corpus("demo-thomas")[:3]

    ranked = reciprocal_rank_fusion(
        [[corpus[0], corpus[1]], [corpus[1], corpus[2]]],
        method="test-rrf",
        limit=3,
    )

    assert ranked[0].evidence.id == corpus[1].id
    assert {item.evidence.id for item in ranked} == {item.id for item in corpus}
    assert all(0 <= item.score <= 1 for item in ranked)
