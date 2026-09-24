"""AI Model Serving Platform.

A small but production-shaped FastAPI service that serves a time-series
forecasting model, and demonstrates the operational concerns a junior
software engineer supporting enterprise AI services is expected to know:
health/readiness probes, structured logging, request metrics, and clean
error handling.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from app.logging_config import configure_logging
from app.metrics import (
    FORECAST_ERRORS,
    MODEL_FIT_SECONDS,
    REQUEST_COUNT,
    REQUEST_LATENCY_SECONDS,
)
from app.model import ForecastModel, InsufficientDataError

configure_logging()
logger = logging.getLogger("forecast_service")

MODEL_VERSION = "holt-winters-v1"
SERVICE_START_TIME = time.time()

# In-memory rolling stats for the dashboard's /stats endpoint. A real
# deployment would read these back out of Prometheus; this keeps the demo
# frontend dependency-free.
_recent_requests: list[dict] = []
_MAX_RECENT = 50


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("service_starting", extra={"model_version": MODEL_VERSION})
    app.state.model = ForecastModel()
    app.state.model_loaded = True
    yield
    logger.info("service_stopping")


app = FastAPI(
    title="AI Model Serving Platform",
    description="Forecasting service with health, metrics, and observability endpoints.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.perf_counter()

    response = None
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        elapsed = time.perf_counter() - start
        route = request.url.path
        REQUEST_COUNT.labels(route=route, method=request.method, status_code=status_code).inc()
        REQUEST_LATENCY_SECONDS.labels(route=route).observe(elapsed)

        if response is not None:
            response.headers["X-Request-ID"] = request_id

        _recent_requests.append(
            {
                "request_id": request_id,
                "route": route,
                "method": request.method,
                "status_code": status_code,
                "latency_ms": round(elapsed * 1000, 2),
                "timestamp": time.time(),
            }
        )
        if len(_recent_requests) > _MAX_RECENT:
            _recent_requests.pop(0)

        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "route": route,
                "method": request.method,
                "status_code": status_code,
                "latency_ms": round(elapsed * 1000, 2),
            },
        )


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class ForecastRequest(BaseModel):
    series: list[float] = Field(..., min_length=1, description="Historical values, oldest first.")
    horizon: int = Field(..., ge=1, le=365, description="Number of future points to forecast.")
    seasonal_periods: int | None = Field(
        default=None, ge=2, description="Optional seasonal period length (e.g. 7 for weekly)."
    )


class ForecastResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    forecast: list[float]
    model_version: str
    model_fit_seconds: float
    seasonal_periods_used: int | None


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float


class ReadyResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    ready: bool
    model_version: str


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["observability"])
async def health() -> HealthResponse:
    """Liveness probe. Should only fail if the process itself is unhealthy."""
    return HealthResponse(status="ok", uptime_seconds=round(time.time() - SERVICE_START_TIME, 1))


@app.get("/ready", response_model=ReadyResponse, tags=["observability"])
async def ready(request: Request) -> ReadyResponse:
    """Readiness probe. Fails if the model hasn't finished loading."""
    model_loaded = getattr(request.app.state, "model_loaded", False)
    if not model_loaded:
        raise HTTPException(status_code=503, detail="model not loaded")
    return ReadyResponse(ready=True, model_version=MODEL_VERSION)


@app.get("/metrics", tags=["observability"])
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/stats", tags=["observability"])
async def stats() -> dict:
    """Lightweight rolling request stats for the dashboard (not a Prometheus replacement)."""
    total = len(_recent_requests)
    errors = sum(1 for r in _recent_requests if r["status_code"] >= 500)
    avg_latency = (
        round(sum(r["latency_ms"] for r in _recent_requests) / total, 2) if total else 0.0
    )
    return {
        "uptime_seconds": round(time.time() - SERVICE_START_TIME, 1),
        "recent_request_count": total,
        "recent_error_count": errors,
        "avg_latency_ms": avg_latency,
        "recent_requests": list(reversed(_recent_requests[-15:])),
    }


@app.post("/v1/forecast", response_model=ForecastResponse, tags=["forecast"])
async def forecast(payload: ForecastRequest, request: Request) -> ForecastResponse:
    model: ForecastModel = request.app.state.model
    try:
        result = model.predict(
            series=payload.series,
            horizon=payload.horizon,
            seasonal_periods=payload.seasonal_periods,
        )
    except InsufficientDataError as exc:
        FORECAST_ERRORS.labels(reason="insufficient_data").inc()
        logger.warning("forecast_rejected", extra={"reason": "insufficient_data"})
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - convert any model failure into a clean 500
        FORECAST_ERRORS.labels(reason="model_error").inc()
        logger.error("forecast_failed", extra={"reason": "model_error"}, exc_info=True)
        raise HTTPException(status_code=500, detail="forecast failed") from exc

    MODEL_FIT_SECONDS.observe(result.model_fit_seconds)
    return ForecastResponse(
        forecast=result.forecast,
        model_version=MODEL_VERSION,
        model_fit_seconds=round(result.model_fit_seconds, 4),
        seasonal_periods_used=result.seasonal_periods_used,
    )
