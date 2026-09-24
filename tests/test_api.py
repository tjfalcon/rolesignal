from fastapi.testclient import TestClient

from api.index import app as vercel_app
from api.main import app

client = TestClient(app)


def test_vercel_entrypoint_exports_the_application() -> None:
    assert vercel_app is app


def test_health_reports_truthful_demo_dependencies() -> None:
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json()["mode"] == "deterministic"
    assert response.json()["database"] == "in-memory-demo"


def test_vercel_prefixed_health_route_matches_public_contract() -> None:
    assert client.get("/api/v1/health").json() == client.get("/v1/health").json()


def test_analyze_returns_citations_for_every_positive_assessment() -> None:
    response = client.post(
        "/v1/analyze",
        json={
            "candidate_profile_id": "demo-thomas",
            "job_text": (
                "Senior engineer role.\n"
                "Required: Build production applications with TypeScript, React, and Next.js.\n"
                "Lead ambiguous cross-functional initiatives and mentor engineers.\n"
                "Build Python FastAPI services for retrieval-augmented generation.\n"
                "Experience with Kubernetes is preferred."
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    evidence_ids = {item["id"] for item in payload["evidence"]}
    positives = [
        item for item in payload["assessments"] if item["status"] in {"supported", "adjacent"}
    ]
    assert positives
    assert all(item["evidence_ids"] for item in positives)
    assert all(set(item["evidence_ids"]) <= evidence_ids for item in positives)


def test_unknown_analysis_is_not_persisted_forever() -> None:
    response = client.get("/v1/analyses/not-present")
    assert response.status_code == 404


def test_rejects_short_or_unknown_profile_inputs() -> None:
    response = client.post(
        "/v1/analyze",
        json={"candidate_profile_id": "private-upload", "job_text": "too short"},
    )
    assert response.status_code == 422
