import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.analyzer import analyze_job
from api.main import app
from api.models import AssessmentStatus, FitAnalysis
from api.retrieval_backends import LocalRetrievalBackend
from evals.fit import (
    CASES_PATH,
    FitCase,
    FitDecision,
    FitSignal,
    FitSuite,
    Review,
    evaluate_case,
    load_suite,
    markdown_report,
    run_baseline,
    summarize,
)
from scripts.evaluate_fit import main


@pytest.fixture
def suite() -> FitSuite:
    return load_suite()


def analyze(case: FitCase) -> FitAnalysis:
    return analyze_job(case.job_text, case.candidate_profile_id, backend=LocalRetrievalBackend())


def test_suite_has_synthetic_provenance_and_spans_required_scenarios(
    suite: FitSuite,
) -> None:
    assert len(suite.cases) >= 12
    assert {case.expected.signal for case in suite.cases} == set(FitSignal)
    assert {"hard-negative", "incomplete", "conflicting", "compound", "confirmed-blocker"} <= {
        tag for case in suite.cases for tag in case.tags
    }
    assert all(
        case.review.reviewer is None for case in suite.cases if case.review.status == "draft"
    )
    assert all(case.source == "authored_synthetic_job" for case in suite.cases)
    assert all(
        not case.candidate_context
        for case in suite.cases
        if case.candidate_profile_id == "demo-thomas"
    )


def test_review_record_requires_reviewer_and_date() -> None:
    with pytest.raises(ValidationError, match="named reviewer"):
        Review(status="reviewed", notes="Test review")
    assert (
        Review(
            status="reviewed",
            reviewer="Test Reviewer",
            reviewed_on=date(2026, 11, 25),
            notes="Test review",
        ).status
        == "reviewed"
    )


@pytest.mark.parametrize(
    "corruption, message",
    [
        ("duplicate_quote", "quotes must be unique"),
        ("quote", "quote the job text"),
        ("evidence", "Expected evidence must resolve"),
        ("exclusion", "Excluded text"),
        ("reason_quote", "labeled requirements"),
        ("reason_evidence", "Finding evidence"),
        ("context", "explicit scenario context"),
    ],
)
def test_fixture_references_fail_closed(suite: FitSuite, corruption: str, message: str) -> None:
    raw = suite.cases[0].model_dump(mode="json")
    if corruption == "duplicate_quote":
        raw["requirements"].append(raw["requirements"][0])
    elif corruption == "quote":
        raw["requirements"][0]["text"] = "This was never in the posting."
    elif corruption == "evidence":
        raw["requirements"][0]["acceptable_evidence_ids"] = ["made-up"]
    elif corruption == "exclusion":
        raw["excluded_texts"] = ["Not in the posting."]
    elif corruption == "reason_quote":
        raw["expected"]["decisive_reason"]["requirement_texts"] = ["made-up"]
    elif corruption == "reason_evidence":
        raw["expected"]["decisive_reason"]["evidence_ids"] = ["made-up"]
    else:
        raw["expected"]["decisive_reason"]["context_keys"] = ["inferred_preference"]
    with pytest.raises(ValidationError, match=message):
        FitCase.model_validate(raw)


def test_duplicate_case_and_changed_profile_snapshot_are_rejected(
    suite: FitSuite,
    tmp_path: Path,
) -> None:
    raw = suite.model_dump(mode="json")
    raw["cases"].append(raw["cases"][0])
    with pytest.raises(ValidationError, match="Case IDs must be unique"):
        FitSuite.model_validate(raw)
    raw = json.loads(CASES_PATH.read_text())
    raw["profile_hashes"]["demo-thomas"] = "changed"
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="review labels"):
        load_suite(path)


def test_real_baseline_keeps_absence_of_verdict_distinct_from_good_predictions(
    suite: FitSuite,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "not-a-real-database")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-never-sent")
    results = run_baseline(suite)
    assert results == run_baseline(suite)
    summary = summarize(results)
    assert summary["decision_count"] == 0
    assert summary["reviewed_cases"] == sum(
        case.review.status == "reviewed" for case in suite.cases
    )
    assert len(summary["missing_decision_case_ids"]) == len(suite.cases)  # type: ignore[arg-type]
    assert summary["false_positive_strong_case_ids"] == []
    assert summary["false_negative_poor_case_ids"] == []
    assert all(result.actual_signal is None and not result.decision_checks for result in results)
    assert all(result.checks.get("citation_integrity", True) for result in results)
    assert all(result.checks.get("assessment_completeness", True) for result in results)
    assert all(result.checks.get("requirement_provenance", True) for result in results)
    rejected = [r.case_id for r in results if r.input_error]
    assert rejected == ["short-blurb"]


def test_evaluation_matches_the_public_api_contract(
    suite: FitSuite,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("api.main.RETRIEVAL_BACKEND", LocalRetrievalBackend())
    client = TestClient(app)
    for case, baseline in zip(suite.cases, run_baseline(suite), strict=True):
        response = client.post(
            "/v1/analyze",
            json={
                "job_text": case.job_text,
                "candidate_profile_id": case.candidate_profile_id,
            },
        )
        if baseline.input_error:
            assert response.status_code == 422
            continue
        assert response.status_code == 200
        result = evaluate_case(case, FitAnalysis.model_validate(response.json()))
        assert result == baseline


def test_decision_comparison_scores_signal_reason_gap_and_unknowns(suite: FitSuite) -> None:
    for case in suite.cases:
        if len(case.job_text) < 80:
            continue
        result = evaluate_case(case, analyze(case), case.expected)
        assert all(result.decision_checks.values())


def test_existing_but_irrelevant_citation_does_not_pass_semantic_reference_check(
    suite: FitSuite,
) -> None:
    case = suite.cases[0]
    analysis = analyze(case).model_copy(deep=True)
    analysis.assessments[0].evidence_ids = ["cb-delivery"]
    result = evaluate_case(case, analysis)
    assert result.checks["citation_integrity"]
    assert not result.checks[f"relevant_citations: {case.requirements[0].text}"]


def test_strong_and_poor_errors_are_tracked_separately_from_missing_verdicts(
    suite: FitSuite,
) -> None:
    strong, poor = suite.cases[0], next(c for c in suite.cases if c.id == "gpu-research")
    overclaim = poor.expected.model_copy(update={"signal": FitSignal.STRONG})
    underclaim = strong.expected.model_copy(update={"signal": FitSignal.POOR})
    results = [
        evaluate_case(poor, analyze(poor), overclaim),
        evaluate_case(strong, analyze(strong), underclaim),
        evaluate_case(poor, analyze(poor)),
    ]
    summary = summarize(results)
    assert summary["decision_count"] == 2
    assert summary["false_positive_strong_case_ids"] == [poor.id]
    assert summary["false_negative_poor_case_ids"] == [strong.id]
    assert summary["missing_decision_case_ids"] == [poor.id]
    assert not results[0].decision_checks["signal"]


def test_wrong_reason_gap_unknown_and_source_are_detected(suite: FitSuite) -> None:
    case = suite.cases[2]
    raw = case.expected.model_dump(mode="json")
    raw["decisive_reason"]["requirement_texts"] = ["Invented job requirement."]
    raw["decisive_reason"]["evidence_ids"] = ["fabricated"]
    raw["decisive_reason"]["context_keys"] = ["inferred_salary"]
    raw["top_gap"] = None
    raw["unknowns"] = []
    decision = FitDecision.model_validate(raw)
    result = evaluate_case(case, analyze(case), decision)
    assert result.decision_checks["signal"]
    assert not any(v for k, v in result.decision_checks.items() if k != "signal")
    assert not evaluate_case(case, None, decision).decision_checks["source_references"]
    # Probability/percentage is deliberately absent from this proposed contract.
    with pytest.raises(ValidationError):
        FitDecision.model_validate({**raw, "hiring_probability": 0.95})


@pytest.mark.parametrize(
    "corruption",
    [
        "empty_citation",
        "dangling_citation",
        "forged_claim",
        "nonpositive_citation",
        "missing_assessment",
        "missing_requirement",
        "invented_requirement",
    ],
)
def test_evaluator_catches_citation_and_extraction_regressions(
    suite: FitSuite,
    corruption: str,
) -> None:
    case = suite.cases[0]
    analysis = analyze(case).model_copy(deep=True)
    if corruption == "empty_citation":
        analysis.assessments[0].evidence_ids = []
    elif corruption == "dangling_citation":
        analysis.assessments[0].evidence_ids = ["not-returned"]
    elif corruption == "forged_claim":
        cited_id = analysis.assessments[0].evidence_ids[0]
        next(e for e in analysis.evidence if e.id == cited_id).claim = "Invented CUDA ownership."
    elif corruption == "nonpositive_citation":
        analysis.assessments[0].status = AssessmentStatus.UNKNOWN
    elif corruption == "missing_assessment":
        analysis.assessments.pop()
    elif corruption == "missing_requirement":
        analysis.requirements.pop()
    else:
        analysis.requirements[0].text = "Invented requirement outside the posting."
    result = evaluate_case(case, analysis)
    assert not all(result.checks.values())
    if corruption in {
        "empty_citation",
        "dangling_citation",
        "forged_claim",
        "nonpositive_citation",
    }:
        assert not result.checks["citation_integrity"]
    if corruption in {"missing_assessment", "missing_requirement"}:
        assert not result.checks["assessment_completeness"]
    if corruption == "invented_requirement":
        assert not result.checks["requirement_provenance"]


def test_report_and_cli_expose_draft_status_and_reject_empty_reviewed_suite(
    suite: FitSuite,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite = suite.model_copy(deep=True)
    for case in suite.cases:
        case.review = Review(notes="Test-only draft review record")
    monkeypatch.setattr("scripts.evaluate_fit.load_suite", lambda: suite)
    report = markdown_report(suite, run_baseline(suite))
    assert f"Reviewed cases: 0/{len(suite.cases)}" in report
    assert "Input rejected" in report
    assert "No requirement checks ran." in report
    assert "Observed requirements:" in report
    assert "(evidence: cb-platform-lead)" in report
    assert "Synthetic scenario context" in report
    assert "unavailable" in report
    assert main(["--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["decision_count"] == 0
    assert main([]) == 0
    assert capsys.readouterr().out == report
    with pytest.raises(SystemExit) as error:
        main(["--reviewed-only"])
    assert error.value.code == 2
    assert "No reviewed fit cases" in capsys.readouterr().err
    reviewed = suite.model_copy(deep=True)
    reviewed.cases[0].review = Review(
        status="reviewed",
        reviewer="Test Reviewer",
        reviewed_on=date(2026, 11, 25),
        notes="Test-only review record",
    )
    monkeypatch.setattr("scripts.evaluate_fit.load_suite", lambda: reviewed)
    assert main(["--reviewed-only", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["reviewed_cases"] == 1
