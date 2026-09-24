import logging
import os
import secrets
import time
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from api.analyzer import analyze_job
from api.models import (
    AnalyzeRequest,
    CandidateProfileDetail,
    EvidenceCreate,
    EvidenceUpdate,
    FitAnalysis,
    HealthResponse,
    ManagedEvidence,
    ResumeVersionCreate,
    ResumeVersionDetail,
)
from api.profile_service import (
    ActiveVersionMutationError,
    InvalidActivationError,
    ProfileNotFoundError,
    ProfileService,
    ProfileStoreUnavailableError,
    VersionNotFoundError,
    create_profile_service,
    require_profile_service,
)
from api.retrieval_backends import RetrievalBackend, create_retrieval_backend

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rolesignal")
RETRIEVAL_BACKEND: RetrievalBackend = create_retrieval_backend()
PROFILE_SERVICE: ProfileService | None = create_profile_service()
ANALYSES: OrderedDict[str, FitAnalysis] = OrderedDict()
MAX_ANALYSES = 50

app = FastAPI(
    title="RoleSignal API",
    description="Evidence-grounded job requirement analysis.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://localhost:3001,"
            "http://127.0.0.1:3000,http://127.0.0.1:3001",
        ).split(",")
        if origin
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-Request-ID", "X-Profile-Admin-Token"],
)


@app.middleware("http")
async def request_context(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s method=%s path=%s status=%s latency_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        round((time.perf_counter() - started) * 1000),
    )
    return response


@app.get("/api/v1/health", response_model=HealthResponse, include_in_schema=False)
@app.get("/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        mode=RETRIEVAL_BACKEND.mode,
        database=RETRIEVAL_BACKEND.database_status(),
        model_provider="available-not-called" if os.getenv("OPENAI_API_KEY") else "not-configured",
    )


@app.post("/api/v1/analyze", response_model=FitAnalysis, include_in_schema=False)
@app.post("/v1/analyze", response_model=FitAnalysis)
def analyze(payload: AnalyzeRequest) -> FitAnalysis:
    analysis = analyze_job(
        payload.job_text,
        payload.candidate_profile_id,
        backend=RETRIEVAL_BACKEND,
    )
    ANALYSES[analysis.analysis_id] = analysis
    while len(ANALYSES) > MAX_ANALYSES:
        ANALYSES.popitem(last=False)
    return analysis


@app.get(
    "/api/v1/analyses/{analysis_id}",
    response_model=FitAnalysis,
    include_in_schema=False,
)
@app.get("/v1/analyses/{analysis_id}", response_model=FitAnalysis)
def get_analysis(analysis_id: str) -> FitAnalysis:
    if analysis_id not in ANALYSES:
        raise HTTPException(status_code=404, detail="Analysis not found or expired")
    return ANALYSES[analysis_id]


def profile_admin_token(
    x_profile_admin_token: str | None = Header(default=None),
) -> None:
    expected = os.getenv("PROFILE_ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Profile administration is not configured",
        )
    if x_profile_admin_token is None or not secrets.compare_digest(x_profile_admin_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")


def profile_service() -> ProfileService:
    try:
        return require_profile_service(PROFILE_SERVICE)
    except ProfileStoreUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


ProfileServiceDependency = Annotated[ProfileService, Depends(profile_service)]


def profile_error(error: Exception) -> HTTPException:
    if isinstance(error, (ProfileNotFoundError, VersionNotFoundError)):
        return HTTPException(status_code=404, detail="Profile or resume version not found")
    if isinstance(error, (ActiveVersionMutationError, InvalidActivationError, ValueError)):
        return HTTPException(status_code=409, detail=str(error))
    raise error


@app.get(
    "/api/v1/profiles/{profile_id}",
    response_model=CandidateProfileDetail,
    include_in_schema=False,
    dependencies=[Depends(profile_admin_token)],
)
@app.get(
    "/v1/profiles/{profile_id}",
    response_model=CandidateProfileDetail,
    dependencies=[Depends(profile_admin_token)],
)
def get_profile(profile_id: str, service: ProfileServiceDependency) -> CandidateProfileDetail:
    try:
        return service.get_profile(profile_id)
    except Exception as error:
        raise profile_error(error) from error


@app.get(
    "/api/v1/resume-versions/{version_id}",
    response_model=ResumeVersionDetail,
    include_in_schema=False,
    dependencies=[Depends(profile_admin_token)],
)
@app.get(
    "/v1/resume-versions/{version_id}",
    response_model=ResumeVersionDetail,
    dependencies=[Depends(profile_admin_token)],
)
def get_resume_version(version_id: str, service: ProfileServiceDependency) -> ResumeVersionDetail:
    try:
        return service.get_version(version_id)
    except Exception as error:
        raise profile_error(error) from error


@app.post(
    "/api/v1/profiles/{profile_id}/resume-versions",
    response_model=ResumeVersionDetail,
    status_code=201,
    include_in_schema=False,
    dependencies=[Depends(profile_admin_token)],
)
@app.post(
    "/v1/profiles/{profile_id}/resume-versions",
    response_model=ResumeVersionDetail,
    status_code=201,
    dependencies=[Depends(profile_admin_token)],
)
def create_resume_version(
    profile_id: str,
    payload: ResumeVersionCreate,
    service: ProfileServiceDependency,
) -> ResumeVersionDetail:
    try:
        return service.create_version(profile_id, payload)
    except Exception as error:
        raise profile_error(error) from error


@app.post(
    "/api/v1/resume-versions/{version_id}/evidence",
    response_model=ManagedEvidence,
    status_code=201,
    include_in_schema=False,
    dependencies=[Depends(profile_admin_token)],
)
@app.post(
    "/v1/resume-versions/{version_id}/evidence",
    response_model=ManagedEvidence,
    status_code=201,
    dependencies=[Depends(profile_admin_token)],
)
def add_resume_evidence(
    version_id: str,
    payload: EvidenceCreate,
    service: ProfileServiceDependency,
) -> ManagedEvidence:
    try:
        return service.add_evidence(version_id, payload)
    except Exception as error:
        raise profile_error(error) from error


@app.patch(
    "/api/v1/resume-versions/{version_id}/evidence/{evidence_id}",
    response_model=ManagedEvidence,
    include_in_schema=False,
    dependencies=[Depends(profile_admin_token)],
)
@app.patch(
    "/v1/resume-versions/{version_id}/evidence/{evidence_id}",
    response_model=ManagedEvidence,
    dependencies=[Depends(profile_admin_token)],
)
def update_resume_evidence(
    version_id: str,
    evidence_id: str,
    payload: EvidenceUpdate,
    service: ProfileServiceDependency,
) -> ManagedEvidence:
    try:
        return service.update_evidence(version_id, evidence_id, payload)
    except Exception as error:
        raise profile_error(error) from error


@app.post(
    "/api/v1/resume-versions/{version_id}/activate",
    response_model=CandidateProfileDetail,
    include_in_schema=False,
    dependencies=[Depends(profile_admin_token)],
)
@app.post(
    "/v1/resume-versions/{version_id}/activate",
    response_model=CandidateProfileDetail,
    dependencies=[Depends(profile_admin_token)],
)
def activate_resume_version(
    version_id: str, service: ProfileServiceDependency
) -> CandidateProfileDetail:
    try:
        return service.activate(version_id)
    except Exception as error:
        raise profile_error(error) from error
