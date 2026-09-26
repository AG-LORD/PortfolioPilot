"""Stored (precomputed) ML forecasts: the nightly job writes them, the
recommendation fast path reads them. Keyed by (ticker, as_of, horizon,
model_version); writing the same key again updates the row."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MLForecast
from app.services.return_providers import Driver, PanelForecast, TickerForecast


def _drivers_to_json(drivers: list[Driver]) -> list[dict]:
    return [{"feature": d.feature, "value": str(d.value), "contribution": str(d.contribution)} for d in drivers]


def _drivers_from_json(rows: list[dict]) -> list[Driver]:
    return [
        Driver(feature=r["feature"], value=Decimal(str(r["value"])), contribution=Decimal(str(r["contribution"])))
        for r in rows
    ]


def upsert_panel_forecast(db: Session, panel: PanelForecast) -> int:
    """Insert or update one row per ticker for panel.as_of; returns the row count."""
    existing = {
        row.ticker: row
        for row in db.scalars(
            select(MLForecast).where(
                MLForecast.as_of == panel.as_of,
                MLForecast.horizon == panel.horizon,
                MLForecast.model_version == panel.model_version,
                MLForecast.ticker.in_(list(panel.forecasts)),
            )
        )
    }
    for ticker, forecast in panel.forecasts.items():
        row = existing.get(ticker)
        if row is None:
            row = MLForecast(ticker=ticker, as_of=panel.as_of, horizon=panel.horizon, model_version=panel.model_version)
            db.add(row)
        row.raw_forecast = Decimal(str(forecast.raw_forecast))
        row.annual_forecast = forecast.annual_forecast
        row.clipped = forecast.clipped
        row.drivers = _drivers_to_json(forecast.drivers)
        row.typical_estimate = forecast.typical_estimate
        row.training_start = panel.training_start
        row.training_end = panel.training_end
        row.training_rows = panel.training_rows
    db.commit()
    return len(panel.forecasts)


def load_stored_forecasts(
    db: Session, tickers: list[str], as_of: date, model_version: str, horizon: int
) -> dict[str, TickerForecast]:
    """Stored forecasts for exactly this as_of and model_version; tickers
    without one are simply absent."""
    if not tickers:
        return {}
    rows = db.scalars(
        select(MLForecast).where(
            MLForecast.ticker.in_(tickers),
            MLForecast.as_of == as_of,
            MLForecast.horizon == horizon,
            MLForecast.model_version == model_version,
        )
    )
    return {
        row.ticker: TickerForecast(
            ticker=row.ticker,
            raw_forecast=float(row.raw_forecast),
            annual_forecast=Decimal(str(row.annual_forecast)),
            clipped=row.clipped,
            drivers=_drivers_from_json(row.drivers),
            typical_estimate=None if row.typical_estimate is None else Decimal(str(row.typical_estimate)),
        )
        for row in rows
    }
