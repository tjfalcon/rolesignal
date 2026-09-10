from api.analyzer import analyze_job, extract_requirements, load_corpus
from api.models import AssessmentStatus, RequirementCategory


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
