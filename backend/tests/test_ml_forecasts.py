"""Stored (nightly) ML forecasts: the store, the provider fast path and the nightly script."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from price_fakes import make_series
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import MLForecast
from app.services import return_providers
from app.services.market_calendar import MARKET_TIMEZONE
from app.services.ml_forecasts import load_stored_forecasts, upsert_panel_forecast
from app.services.return_providers import (
    FORECAST_ON_REQUEST,
    FORECAST_PRECOMPUTED,
    ML,
    ML_MODEL_VERSION,
    Driver,
    MLForecastProvider,
    PanelForecast,
    TickerForecast,
    fit_and_forecast,
)
from scripts import nightly_jobs
from scripts.take_daily_snapshots import EXIT_FAILED, EXIT_NON_TRADING_DAY

END = date(2025, 12, 31)
TICKERS = [f"ZZTEST_{c}" for c in "ABCDEF"]
AS_OF = date(2025, 12, 31)


def _prices(n_days=700):
    return {t: make_series(i, n_days=n_days, end=END, weekdays_only=True) for i, t in enumerate(TICKERS)}


def _stored(ticker, annual="0.1234"):
    return TickerForecast(
        ticker=ticker,
        raw_forecast=0.0098,
        annual_forecast=Decimal(annual),
        clipped=False,
        drivers=[Driver(feature="momentum_20", value=Decimal("0.05"), contribution=Decimal("0.01"))],
        typical_estimate=Decimal("0.08"),
    )


def _panel(annual="0.1234", as_of=AS_OF, model_version=ML_MODEL_VERSION):
    return PanelForecast(
        as_of=as_of,
        horizon=20,
        model_version=model_version,
        forecasts={t: _stored(t, annual) for t in TICKERS[:3]},
        clip_bounds=(-0.15, 0.17),
        training_start=date(2021, 1, 4),
        training_end=date(2025, 12, 2),
        training_rows=5000,
    )


@pytest.fixture
def sqlite_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def register_now_function(connection, _record):
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _no_fit(monkeypatch):
    def forbidden(name):
        pytest.fail("the fast path must not fit a model")

    monkeypatch.setattr(return_providers, "make_model", forbidden)


# --- provider fast path ---------------------------------------------------------------


def test_fast_path_returns_stored_values_without_fitting(monkeypatch):
    _no_fit(monkeypatch)
    stored = {t: _stored(t, annual=f"0.1{i}") for i, t in enumerate(TICKERS)}
    estimate = MLForecastProvider(stored=stored, stored_as_of=AS_OF).estimate(_prices())

    assert estimate.forecast_source == FORECAST_PRECOMPUTED
    assert estimate.forecast_as_of == AS_OF
    assert estimate.model_version == ML_MODEL_VERSION
    for i, t in enumerate(TICKERS):
        assert estimate.expected_returns[t] == Decimal(f"0.1{i}")
        assert estimate.sources[t] == ML
        assert estimate.drivers[t] == stored[t].drivers
        assert estimate.typical_estimates[t] == Decimal("0.08")


def test_fast_path_ignores_stored_tickers_that_were_not_requested(monkeypatch):
    _no_fit(monkeypatch)
    prices = {t: p for t, p in _prices().items() if t in TICKERS[:2]}
    stored = {t: _stored(t) for t in TICKERS}
    estimate = MLForecastProvider(stored=stored, stored_as_of=AS_OF).estimate(prices)
    assert set(estimate.expected_returns) == set(TICKERS[:2])


def test_missing_stored_tickers_are_forecast_on_request():
    prices = _prices()
    stored = {TICKERS[0]: _stored(TICKERS[0], annual="0.5")}
    estimate = MLForecastProvider(stored=stored, stored_as_of=AS_OF).estimate(prices)
    on_request = fit_and_forecast(prices)

    assert estimate.forecast_source == FORECAST_ON_REQUEST
    assert estimate.expected_returns[TICKERS[0]] == Decimal("0.5")
    for t in TICKERS[1:]:
        assert estimate.expected_returns[t] == on_request.forecasts[t].annual_forecast


def test_without_stored_forecasts_the_on_request_path_is_unchanged():
    prices = _prices()
    estimate = MLForecastProvider().estimate(prices)
    fitted = fit_and_forecast(prices)
    assert estimate.forecast_source == FORECAST_ON_REQUEST
    assert estimate.forecast_as_of == fitted.as_of
    assert {t: estimate.expected_returns[t] for t in fitted.forecasts} == {
        t: f.annual_forecast for t, f in fitted.forecasts.items()
    }


# --- store --------------------------------------------------------------------------


def test_stale_as_of_or_other_model_version_is_not_loaded(sqlite_db):
    upsert_panel_forecast(sqlite_db, _panel())

    assert set(load_stored_forecasts(sqlite_db, TICKERS, AS_OF, ML_MODEL_VERSION, 20)) == set(TICKERS[:3])
    # The next trading day has nothing stored yet (yesterday's forecasts are stale).
    assert load_stored_forecasts(sqlite_db, TICKERS, AS_OF + timedelta(days=1), ML_MODEL_VERSION, 20) == {}
    assert load_stored_forecasts(sqlite_db, TICKERS, AS_OF, "some-other-model-v2", 20) == {}


def test_stored_forecasts_round_trip(sqlite_db):
    upsert_panel_forecast(sqlite_db, _panel())
    loaded = load_stored_forecasts(sqlite_db, [TICKERS[0]], AS_OF, ML_MODEL_VERSION, 20)[TICKERS[0]]
    assert loaded == _stored(TICKERS[0])


def test_upsert_is_idempotent(sqlite_db):
    upsert_panel_forecast(sqlite_db, _panel(annual="0.1"))
    upsert_panel_forecast(sqlite_db, _panel(annual="0.1"))
    upsert_panel_forecast(sqlite_db, _panel(annual="0.2"))

    assert sqlite_db.scalar(select(func.count()).select_from(MLForecast)) == 3
    loaded = load_stored_forecasts(sqlite_db, TICKERS, AS_OF, ML_MODEL_VERSION, 20)
    assert {f.annual_forecast for f in loaded.values()} == {Decimal("0.2")}


# --- nightly script -------------------------------------------------------------------


class _FakeSession:
    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


def test_nightly_continues_after_a_stage_fails(monkeypatch):
    calls = []

    def failing(db, now):
        calls.append("snapshots")
        raise RuntimeError("snapshot boom")

    def ok(name):
        def stage(db, now):
            calls.append(name)
            return nightly_jobs.StageResult(name, ok=True, detail="fine")

        return stage

    monkeypatch.setattr(
        nightly_jobs, "STAGES", [("snapshots", failing), ("prices", ok("prices")), ("forecasts", ok("forecasts"))]
    )
    db = _FakeSession()
    friday_evening = datetime(2026, 9, 25, 17, 0, tzinfo=MARKET_TIMEZONE)
    summary = nightly_jobs.run_nightly(db, friday_evening)

    assert calls == ["snapshots", "prices", "forecasts"]
    assert [(s.name, s.ok) for s in summary.stages] == [("snapshots", False), ("prices", True), ("forecasts", True)]
    assert "snapshot boom" in summary.stages[0].detail
    assert db.rollbacks == 1
    assert nightly_jobs.exit_code(summary) == EXIT_FAILED


def test_nightly_exits_with_the_non_trading_day_code_on_weekends():
    saturday_evening = datetime(2026, 9, 26, 18, 0, tzinfo=MARKET_TIMEZONE)
    summary = nightly_jobs.run_nightly(None, saturday_evening)
    assert summary.ran is False
    assert nightly_jobs.exit_code(summary) == EXIT_NON_TRADING_DAY
