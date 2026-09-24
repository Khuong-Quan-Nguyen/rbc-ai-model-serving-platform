# AI Model Serving Platform

A small, production-shaped service that serves a time-series forecasting
model behind a FastAPI backend — built to demonstrate the operational
skills an entry-level Software Engineer on an enterprise AI team is
expected to grow into: reliable APIs, containerization, CI/CD, testing,
and observability.

Built for RBC's **AI Group — Software Engineer (0–2 years)** posting
(Toronto), which centers on *supporting* production AI infrastructure
rather than building models from scratch. This project is scoped
around that: a real (small) ML model, wrapped in the engineering
practices the posting explicitly asks for.

## What it does

The service fits a [Holt-Winters exponential smoothing model](https://www.statsmodels.org/stable/generated/statsmodels.tsa.holtwinters.ExponentialSmoothing.html)
(via `statsmodels`) on a user-supplied time series and returns a forecast.
A dashboard lets you watch the service's live health and request traffic,
and run forecasts from the browser.

## Why this project, mapped to the job posting

| Posting asks for | Where it is here |
|---|---|
| Building reliable APIs / backend services for AI apps | `app/main.py` — FastAPI service, Pydantic validation, clean error handling |
| Container technologies (Docker/Kubernetes) | `Dockerfile`, `docker-compose.yml`, `k8s/` manifests |
| CI/CD pipelines | `.github/workflows/ci.yml` — lint → test → build → deploy |
| Unit tests, integration tests, documentation | `tests/test_model.py` (unit), `tests/test_api.py` (integration), this README |
| Observability: logging, monitoring, alerting | `app/logging_config.py` (structured JSON logs), `app/metrics.py` (Prometheus), `alerts/rules.yml` |
| Troubleshooting / production support | `/health`, `/ready`, `/stats`, request-ID tracing on every response |
| Secure coding practices | Non-root Docker user, read-only root filesystem in K8s, dropped Linux capabilities |

## Architecture

```
┌─────────────┐      ┌──────────────────────┐      ┌────────────┐
│  Dashboard  │─────▶│   FastAPI service    │─────▶│ Holt-Winters│
│ (frontend/) │◀─────│  app/main.py          │◀─────│   model    │
└─────────────┘      │  + logging middleware │      └────────────┘
                      │  + Prometheus metrics │
                      └──────────┬───────────┘
                                 │ /metrics
                                 ▼
                        ┌─────────────────┐
                        │   Prometheus     │──▶ alerts/rules.yml
                        └─────────────────┘
```

In Kubernetes, the same container runs as a `Deployment` with liveness,
readiness, and startup probes, fronted by a `Service`, scaled by an `HPA`,
and protected during rollouts/maintenance by a `PodDisruptionBudget`.

## Running it locally (no Docker required)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements-dev.txt

uvicorn app.main:app --reload --port 8000
```

In a second terminal, serve the dashboard:

```bash
cd frontend
python -m http.server 8080
```

Open `http://localhost:8080`. The dashboard talks to the API at
`http://localhost:8000` (CORS is open for local development).

## Running it with Docker

```bash
docker compose up --build
```

This starts the service on `:8000` and Prometheus (pre-configured to scrape
it, with `alerts/rules.yml` loaded) on `:9090`.

## Running on Kubernetes

Requires a local cluster (`kind`, `minikube`, or Docker Desktop's
Kubernetes) and a built image available to it:

```bash
docker build -t forecast-service:latest .
# kind: kind load docker-image forecast-service:latest
# minikube: minikube image load forecast-service:latest

kubectl apply -f k8s/
kubectl -n ai-model-serving get pods
kubectl -n ai-model-serving port-forward svc/forecast-service 8000:80
```

## Testing

```bash
pytest tests/ -v --cov=app --cov-report=term-missing
ruff check app tests
```

Currently: 15 tests, 95% coverage.

## API reference

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/health` | Liveness probe |
| `GET`  | `/ready`  | Readiness probe (model loaded) |
| `GET`  | `/metrics` | Prometheus scrape target |
| `GET`  | `/stats` | Rolling request stats, used by the dashboard |
| `POST` | `/v1/forecast` | Fit + forecast on a supplied series |

`POST /v1/forecast` body:

```json
{
  "series": [10, 12, 13, 12, 15, 17, 16, 19, 21, 20],
  "horizon": 4,
  "seasonal_periods": null
}
```

## Known limitations / follow-ups

Being upfront about what this doesn't do, rather than overstating it:

- The model is refit on every request rather than cached — fine for a demo,
  but a real fixed-series deployment would fit once at startup (or on a
  schedule) and serve from the fitted model.
- `/stats` is an in-memory rolling window for the dashboard demo, not a
  substitute for querying Prometheus directly — it resets on restart and
  isn't shared across replicas.
- The CI pipeline builds the Docker image but doesn't push to a registry
  or apply the K8s manifests to a live cluster, since this repo has no
  registry or cluster credentials configured. The `deploy` job documents
  where that would plug in.
- CORS is wide open (`allow_origins=["*"]`) for local dev convenience —
  a real deployment would restrict this to the actual frontend origin.
