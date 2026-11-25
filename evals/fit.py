"""Evaluate whole job decisions without substituting retrieval coverage for fit."""

import hashlib
from collections import Counter
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from api.analyzer import analyze_job, load_fixture_corpus
from api.models import AnalyzeRequest, AssessmentStatus, FitAnalysis, Importance
from api.retrieval_backends import LocalRetrievalBackend

CASES_PATH = Path(__file__).with_name("fit_cases.json")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FitSignal(StrEnum):
    STRONG = "strong_fit"
    PLAUSIBLE = "plausible_fit"
    STRETCH = "stretch"
    POOR = "poor_fit"
    INSUFFICIENT = "insufficient_information"


class Finding(StrictModel):
    explanation: str = Field(min_length=1)
    requirement_texts: list[str]
    evidence_ids: list[str]
    context_keys: list[str] = Field(default_factory=list)


class FitDecision(StrictModel):
    """Proposed synthesis contract, not yet returned by the public API.

    Exact requirement quotes and evidence IDs make reason selection inspectable.
    Free-text explanation quality still needs human review.
    """

    signal: FitSignal
    decisive_reason: Finding
    top_gap: Finding | None
    unknowns: list[str]
    needs_review: bool
    what_would_change: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_attention_for_unknowns(self) -> Self:
        if self.needs_review != bool(self.unknowns):
            raise ValueError("needs_review must reflect unresolved unknowns, independently of fit")
        return self


class RequirementExpectation(StrictModel):
    text: str = Field(min_length=1)
    role: Literal["core", "mandatory", "preference", "constraint"]
    importance: Importance
    allowed_statuses: list[AssessmentStatus] = Field(min_length=1)
    acceptable_evidence_ids: list[str]


class Review(StrictModel):
    status: Literal["draft", "reviewed"] = "draft"
    reviewer: str | None = None
    reviewed_on: date | None = None
    notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_review_record(self) -> Self:
        if self.status == "reviewed" and (not self.reviewer or not self.reviewed_on):
            raise ValueError("Reviewed cases require a named reviewer and review date")
        return self


class FitCase(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    tags: list[str] = Field(min_length=1)
    source: Literal["authored_synthetic_job"]
    candidate_profile_id: Literal["demo-thomas", "synthetic"]
    # Scenario-only facts, never added to the reusable candidate fixture.
    candidate_context: dict[str, str] = Field(default_factory=dict)
    job_text: str = Field(min_length=1, max_length=30_000)
    requirements: list[RequirementExpectation]
    excluded_texts: list[str] = Field(default_factory=list)
    expected: FitDecision
    review: Review

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        corpus_ids = {item.id for item in load_fixture_corpus(self.candidate_profile_id)}
        texts = [item.text for item in self.requirements]
        if len(texts) != len(set(texts)):
            raise ValueError("Requirement quotes must be unique within a case")
        for item in self.requirements:
            if item.text not in self.job_text:
                raise ValueError("Expected requirements must quote the job text")
            if not set(item.acceptable_evidence_ids) <= corpus_ids:
                raise ValueError("Expected evidence must resolve to the pinned fixture")
        for text in self.excluded_texts:
            if text not in self.job_text or text in texts:
                raise ValueError("Excluded text must quote non-requirement job content")
        findings = [self.expected.decisive_reason]
        if self.expected.top_gap is not None:
            findings.append(self.expected.top_gap)
        for finding in findings:
            if not set(finding.requirement_texts) <= set(texts):
                raise ValueError("Findings must reference labeled requirements")
            if not set(finding.evidence_ids) <= corpus_ids:
                raise ValueError("Finding evidence must resolve to the pinned fixture")
            if not set(finding.context_keys) <= self.candidate_context.keys():
                raise ValueError("Findings must reference explicit scenario context")
        return self


class FitSuite(StrictModel):
    rubric_version: str
    rubric_status: Literal["draft", "reviewed"]
    profile_hashes: dict[str, str]
    cases: list[FitCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_cases(self) -> Self:
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Case IDs must be unique")
        return self


class ObservedRequirement(StrictModel):
    text: str
    status: AssessmentStatus | None
    evidence_ids: list[str]


class CaseResult(StrictModel):
    case_id: str
    review_status: str
    expected_signal: FitSignal
    actual_signal: FitSignal | None
    expected_needs_review: bool
    actual_needs_review: bool | None
    input_error: str | None
    checks: dict[str, bool]
    decision_checks: dict[str, bool]
    observed_requirements: list[ObservedRequirement]


def load_suite(path: Path = CASES_PATH) -> FitSuite:
    suite = FitSuite.model_validate_json(path.read_text())
    for case in suite.cases:
        corpus = load_fixture_corpus(case.candidate_profile_id)
        snapshot = "\n".join(item.model_dump_json() for item in corpus)
        digest = hashlib.sha256(snapshot.encode()).hexdigest()
        if suite.profile_hashes.get(case.candidate_profile_id) != digest:
            raise ValueError("Candidate fixture changed; review labels before updating its hash")
    return suite


def evaluate_case(
    case: FitCase,
    analysis: FitAnalysis | None,
    decision: FitDecision | None = None,
    *,
    input_error: str | None = None,
) -> CaseResult:
    """Check source-backed assertions; absent decisions are reported separately."""
    checks: dict[str, bool] = {}
    observed: list[ObservedRequirement] = []
    requirements = {item.text: item for item in analysis.requirements} if analysis else {}
    assessments = {item.requirement_id: item for item in analysis.assessments} if analysis else {}
    evidence_ids = {item.id for item in analysis.evidence} if analysis else set()
    fixture = {item.id: item for item in load_fixture_corpus(case.candidate_profile_id)}
    if analysis is not None:
        # Resolving IDs alone cannot establish semantic entailment. Check against
        # the pinned source too; labeled expectations below check relevant IDs.
        checks["citation_integrity"] = all(
            bool(item.evidence_ids)
            and set(item.evidence_ids) <= evidence_ids
            and all(
                fixture.get(e.id) == e and e.visibility == "public"
                for e in analysis.evidence
                if e.id in item.evidence_ids
            )
            if item.status in {AssessmentStatus.SUPPORTED, AssessmentStatus.ADJACENT}
            else not item.evidence_ids
            for item in analysis.assessments
        )
        checks["assessment_completeness"] = len(assessments) == len(analysis.assessments) == len(
            requirements
        ) and set(assessments) == {item.id for item in requirements.values()}
        checks["requirement_provenance"] = all(
            item.text in case.job_text for item in analysis.requirements
        )
        checks["no_unlabeled_requirements"] = set(requirements) <= {
            item.text for item in case.requirements
        }
        for text, requirement in requirements.items():
            assessment = assessments.get(requirement.id)
            observed.append(
                ObservedRequirement(
                    text=text,
                    status=assessment.status if assessment else None,
                    evidence_ids=assessment.evidence_ids if assessment else [],
                )
            )
    for expected in case.requirements:
        expected_requirement = requirements.get(expected.text)
        assessment = assessments.get(expected_requirement.id) if expected_requirement else None
        prefix = expected.text
        checks[f"extracted: {prefix}"] = expected_requirement is not None
        checks[f"importance: {prefix}"] = bool(
            expected_requirement and expected_requirement.importance == expected.importance
        )
        checks[f"assessment: {prefix}"] = bool(
            assessment and assessment.status in expected.allowed_statuses
        )
        checks[f"relevant_citations: {prefix}"] = bool(
            assessment
            and (
                bool(assessment.evidence_ids)
                and set(assessment.evidence_ids) <= set(expected.acceptable_evidence_ids)
                if expected.acceptable_evidence_ids
                else not assessment.evidence_ids
            )
        )
    for text in case.excluded_texts:
        checks[f"excluded: {text}"] = not any(text in item for item in requirements)

    decision_checks: dict[str, bool] = {}
    if decision is not None:
        wanted = case.expected
        decision_checks["signal"] = decision.signal == wanted.signal
        decision_checks["decisive_requirements"] = set(
            decision.decisive_reason.requirement_texts
        ) == set(wanted.decisive_reason.requirement_texts)
        decision_checks["decisive_evidence"] = set(decision.decisive_reason.evidence_ids) == set(
            wanted.decisive_reason.evidence_ids
        )
        decision_checks["decisive_context"] = set(decision.decisive_reason.context_keys) == set(
            wanted.decisive_reason.context_keys
        )
        decision_checks["top_gap"] = (
            decision.top_gap is None
            if wanted.top_gap is None
            else decision.top_gap is not None
            and set(decision.top_gap.requirement_texts) == set(wanted.top_gap.requirement_texts)
            and set(decision.top_gap.evidence_ids) == set(wanted.top_gap.evidence_ids)
            and set(decision.top_gap.context_keys) == set(wanted.top_gap.context_keys)
        )
        decision_checks["unknowns"] = set(decision.unknowns) == set(wanted.unknowns)
        decision_checks["needs_review"] = decision.needs_review == wanted.needs_review
        findings = [decision.decisive_reason] + ([decision.top_gap] if decision.top_gap else [])
        decision_checks["source_references"] = analysis is not None and all(
            set(item.requirement_texts) <= requirements.keys()
            and set(item.evidence_ids) <= evidence_ids & fixture.keys()
            and set(item.context_keys) <= case.candidate_context.keys()
            for item in findings
        )
    return CaseResult(
        case_id=case.id,
        review_status=case.review.status,
        expected_signal=case.expected.signal,
        actual_signal=decision.signal if decision else None,
        expected_needs_review=case.expected.needs_review,
        actual_needs_review=decision.needs_review if decision else None,
        input_error=input_error,
        checks=checks,
        decision_checks=decision_checks,
        observed_requirements=observed,
    )


def run_baseline(suite: FitSuite) -> list[CaseResult]:
    results = []
    for case in suite.cases:
        try:
            payload = AnalyzeRequest(
                job_text=case.job_text, candidate_profile_id=case.candidate_profile_id
            )
        except ValidationError:
            results.append(evaluate_case(case, None, input_error="request_validation"))
            continue
        analysis = analyze_job(
            payload.job_text, payload.candidate_profile_id, backend=LocalRetrievalBackend()
        )
        results.append(evaluate_case(case, analysis))
    return results


def summarize(results: list[CaseResult]) -> dict[str, object]:
    available = [item for item in results if item.actual_signal is not None]
    return {
        "cases": len(results),
        "reviewed_cases": sum(item.review_status == "reviewed" for item in results),
        "decision_count": len(available),
        "missing_decision_case_ids": [r.case_id for r in results if r.actual_signal is None],
        "false_positive_strong_case_ids": [
            r.case_id
            for r in available
            if r.actual_signal == FitSignal.STRONG and r.expected_signal != FitSignal.STRONG
        ],
        "false_negative_poor_case_ids": [
            r.case_id
            for r in available
            if r.actual_signal == FitSignal.POOR and r.expected_signal != FitSignal.POOR
        ],
        "confusion_counts": dict(
            Counter(f"{r.expected_signal} -> {r.actual_signal or 'unavailable'}" for r in results)
        ),
        "requirement_checks_passed": sum(sum(r.checks.values()) for r in results),
        "requirement_checks_total": sum(len(r.checks) for r in results),
    }


def markdown_report(suite: FitSuite, results: list[CaseResult]) -> str:
    summary = summarize(results)
    lines = [
        "# Core fit baseline",
        "",
        f"Rubric: `{suite.rubric_version}` ({suite.rubric_status}). "
        f"Reviewed cases: {summary['reviewed_cases']}/{len(results)}.",
        "",
        "All jobs are authored synthetic examples. Candidate evidence is pinned to the "
        "repository's sanitized fixtures. Draft expectations are proposals, "
        "not Thomas's judgments.",
        "",
        "The current analyzer returns no overall fit decision. Unavailable decisions are not "
        "correct predictions or classification errors. Evidence coverage is not used as a verdict.",
        "",
        "Unknown salary, location, or work authorization does not cap an otherwise strong match. "
        "The proposed Needs review indicator is separate from the fit signal.",
        "",
        f"Available decisions: {summary['decision_count']}/{len(results)}. "
        f"Requirement checks: {summary['requirement_checks_passed']}/"
        f"{summary['requirement_checks_total']} passed.",
        "",
        "False-positive strong and false-negative poor lists are reported in JSON only for "
        "available decisions; empty lists with no decisions do not establish quality.",
        "",
        "Candidate scenario context and free-text reason quality require human review. "
        "The current analyzer does not consume scenario context.",
        "",
        "| Case | Proposed signal | Proposed attention | Actual signal | Failed checks |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for result in results:
        failed_count = sum(not v for v in result.checks.values())
        attention = "Needs review" if result.expected_needs_review else "None"
        lines.append(
            f"| {result.case_id} | {result.expected_signal} | {attention} | "
            f"{result.actual_signal or 'unavailable'} | {failed_count} |"
        )
    for case, result in zip(suite.cases, results, strict=True):
        lines.extend(
            [
                "",
                f"## {case.id}",
                "",
                f"Review: {case.review.status}.",
                "",
                "```text",
                case.job_text,
                "```",
                "",
                f"Proposed decisive reason: {case.expected.decisive_reason.explanation}",
                "",
                "Proposed top gap: "
                + (
                    case.expected.top_gap.explanation
                    if case.expected.top_gap
                    else "None identified."
                ),
                "",
                "Unknowns: " + ", ".join(case.expected.unknowns) + ".",
                "",
                f"What would change it: {case.expected.what_would_change}",
                "",
            ]
        )
        if case.candidate_context:
            lines.append(f"Synthetic scenario context: {case.candidate_context}")
            lines.append("")
        if result.input_error:
            lines.extend([f"Input rejected: `{result.input_error}`.", ""])
        if result.observed_requirements:
            lines.extend(["Observed requirements:", ""])
            for observed in result.observed_requirements:
                citations = ", ".join(observed.evidence_ids)
                lines.append(
                    f"- {observed.status}: {observed.text} (evidence: {citations or 'none'})"
                )
            lines.append("")
        failures = [name for name, passed in result.checks.items() if not passed]
        if failures:
            lines.extend(["Failed requirement checks:", ""])
            lines.extend(f"- {name}" for name in failures)
        else:
            lines.append(
                "All requirement checks passed." if result.checks else "No requirement checks ran."
            )
    return "\n".join(lines) + "\n"
