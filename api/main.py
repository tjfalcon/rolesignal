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

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rolesignal")
MODE = "deterministic"
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
        origin for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if origin
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


@app.get("/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        mode=MODE,
        database="in-memory-demo",
        model_provider="available-not-called" if os.getenv("OPENAI_API_KEY") else "not-configured",
    )


@app.post("/v1/analyze", response_model=FitAnalysis)
def analyze(payload: AnalyzeRequest) -> FitAnalysis:
    analysis = analyze_job(payload.job_text, payload.candidate_profile_id, MODE)
    ANALYSES[analysis.analysis_id] = analysis
    while len(ANALYSES) > MAX_ANALYSES:
        ANALYSES.popitem(last=False)
    return analysis


@app.get("/v1/analyses/{analysis_id}", response_model=FitAnalysis)
def get_analysis(analysis_id: str) -> FitAnalysis:
    if analysis_id not in ANALYSES:
        raise HTTPException(status_code=404, detail="Analysis not found or expired")
    return ANALYSES[analysis_id]
