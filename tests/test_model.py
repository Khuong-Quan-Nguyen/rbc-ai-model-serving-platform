import pytest

from app.model import ForecastModel, InsufficientDataError


def test_predict_returns_correct_horizon_length():
    model = ForecastModel()
    series = [10, 12, 13, 12, 15, 17, 16, 19, 21, 20]
    result = model.predict(series, horizon=3)
    assert len(result.forecast) == 3
    assert all(isinstance(v, float) for v in result.forecast)


def test_predict_rejects_zero_horizon():
    model = ForecastModel()
    with pytest.raises(ValueError):
        model.predict([1, 2, 3, 4, 5], horizon=0)


def test_predict_raises_on_insufficient_non_seasonal_data():
    model = ForecastModel()
    with pytest.raises(InsufficientDataError):
        model.predict([1, 2], horizon=1)


def test_predict_raises_on_insufficient_seasonal_data():
    model = ForecastModel()
    with pytest.raises(InsufficientDataError):
        # seasonal_periods=7 needs at least 14 points
        model.predict(list(range(10)), horizon=1, seasonal_periods=7)


def test_predict_seasonal_path_reports_periods_used():
    model = ForecastModel()
    series = [10 + (i % 7) for i in range(21)]
    result = model.predict(series, horizon=2, seasonal_periods=7)
    assert result.seasonal_periods_used == 7
    assert len(result.forecast) == 2


def test_predict_model_fit_seconds_is_recorded():
    model = ForecastModel()
    result = model.predict([1, 2, 3, 4, 5, 6], horizon=1)
    assert result.model_fit_seconds >= 0
