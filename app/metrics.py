"""Prometheus metrics for the service.

Exposed at GET /metrics in Prometheus text format. A real deployment would
point a Prometheus server's scrape config at this endpoint; alerts/rules.yml
in this repo defines example alerting rules that consume these metrics.
"""
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "forecast_service_requests_total",
    "Total HTTP requests received, labeled by route, method, and status code.",
    ["route", "method", "status_code"],
)

REQUEST_LATENCY_SECONDS = Histogram(
    "forecast_service_request_latency_seconds",
    "Request latency in seconds, labeled by route.",
    ["route"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

FORECAST_ERRORS = Counter(
    "forecast_service_forecast_errors_total",
    "Number of forecast requests that failed model fitting/validation.",
    ["reason"],
)

MODEL_FIT_SECONDS = Histogram(
    "forecast_service_model_fit_seconds",
    "Time spent fitting the Holt-Winters model per request.",
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 2),
)
