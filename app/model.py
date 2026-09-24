"""Forecasting model wrapper.

Wraps a Holt-Winters exponential smoothing model (statsmodels) behind a
small, testable interface so the serving layer (FastAPI) never touches
statsmodels directly. Keeping this boundary clean is what makes the model
swappable later without touching API/observability code.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from statsmodels.tsa.holtwinters import ExponentialSmoothing


class InsufficientDataError(ValueError):
    """Raised when there isn't enough history to fit a seasonal model."""


@dataclass
class ForecastResult:
    forecast: list[float]
    model_fit_seconds: float
    seasonal_periods_used: int | None


class ForecastModel:
    """Fits a Holt-Winters model on demand and produces a forecast.

    This is intentionally stateless across requests (no cached fitted
    model) because each request may bring a different series. For a
    fixed-series production use case you would fit once at startup and
    reuse the fitted model — noted in the README as a scaling follow-up.
    """

    MIN_POINTS_NON_SEASONAL = 4
    MIN_POINTS_SEASONAL_MULTIPLIER = 2

    def predict(
        self,
        series: list[float],
        horizon: int,
        seasonal_periods: int | None = None,
    ) -> ForecastResult:
        if horizon < 1:
            raise ValueError("horizon must be >= 1")

        values = np.asarray(series, dtype=float)

        use_seasonal = seasonal_periods is not None and seasonal_periods > 1
        min_required = (
            seasonal_periods * self.MIN_POINTS_SEASONAL_MULTIPLIER
            if use_seasonal
            else self.MIN_POINTS_NON_SEASONAL
        )
        if len(values) < min_required:
            raise InsufficientDataError(
                f"Need at least {min_required} data points "
                f"(got {len(values)}) for the requested configuration."
            )

        start = time.perf_counter()
        model = ExponentialSmoothing(
            values,
            trend="add",
            seasonal="add" if use_seasonal else None,
            seasonal_periods=seasonal_periods if use_seasonal else None,
            initialization_method="estimated",
        )
        fitted = model.fit(optimized=True)
        elapsed = time.perf_counter() - start

        prediction = fitted.forecast(horizon)
        return ForecastResult(
            forecast=[float(v) for v in prediction],
            model_fit_seconds=elapsed,
            seasonal_periods_used=seasonal_periods if use_seasonal else None,
        )
