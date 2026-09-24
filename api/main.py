import logging
import os
import time
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from api.analyzer import analyze_job
from api.models import AnalyzeRequest, FitAnalysis, HealthResponse
from api.retrieval_backends import RetrievalBackend, create_retrieval_backend

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rolesignal")
RETRIEVAL_BACKEND: RetrievalBackend = create_retrieval_backend()
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
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID"],
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
