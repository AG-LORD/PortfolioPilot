from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Portfolio, RecommendationSnapshot, RiskProfile, UserProfile
from app.services import stock_analysis as stock_analysis_service
from app.services.market_data import MarketDataUnavailableError, PricePoint
from app.services.price_history import PriceHistory
from app.services.stock_analysis import get_stock_analysis


@pytest.fixture
def stock_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def register_now_function(connection, _record):
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user_id = uuid4()
    risk_profile = RiskProfile(
        user_id=user_id,
        score=Decimal("50"),
        category="moderate",
        max_position_weight=Decimal("0.2"),
        max_sector_weight=Decimal("0.4"),
        drift_threshold=Decimal("0.05"),
        target_volatility=Decimal("0.15"),
    )
    session.add(UserProfile(id=user_id))
    session.add(risk_profile)
    session.flush()
    portfolio = Portfolio(
        user_id=user_id,
        risk_profile_id=risk_profile.id,
        name="Stock analysis portfolio",
        purpose=None,
        base_currency="INR",
        initial_capital=Decimal("10000"),
        cash_balance=Decimal("9900"),
    )
    session.add(portfolio)
    session.commit()
    yield session, user_id, portfolio
    session.close()
    engine.dispose()


def _points(count=320):
    start = date(2025, 1, 1)
    points = []
    close = Decimal("100")
    for index in range(count):
        day = start + timedelta(days=index)
        close *= Decimal("1.001")
        points.append(
            PricePoint(
                date=day,
                open=close - Decimal("1"),
                high=close + Decimal("2"),
                low=close - Decimal("2"),
                close=close,
                volume=1000 + index,
            )
        )
    return points


def _set_history(monkeypatch, ticker, points):
    monkeypatch.setattr(
        stock_analysis_service.price_history,
        "get_price_history",
        lambda _db, tickers, _start, _end: PriceHistory(
            points={ticker: points} if ticker in tickers else {}
        ),
    )


def test_stock_analysis_returns_actual_history_indicators_and_returns(stock_db, monkeypatch):
    session, _, _ = stock_db
    points = _points()
    _set_history(monkeypatch, "TCS", points)
    monkeypatch.setattr(
        stock_analysis_service.market_data,
        "get_current_price",
        lambda _ticker: Decimal("500"),
    )

    result = get_stock_analysis(session, uuid4(), " tcs.ns ")

    assert result.ticker == "TCS"
    assert result.current_price == Decimal("500")
    assert result.current_quote_available is True
    assert result.latest_close == points[-1].close
    assert result.latest_close_date == points[-1].date
    assert len(result.historical_prices) == 252
    assert set(result.technical_indicators) >= {
        "close_to_sma_20",
        "rsi_14",
        "macd_line",
        "realized_vol_20",
    }
    assert result.return_20d is not None
    assert result.return_60d is not None
    assert result.return_252d is not None
    assert result.annualized_volatility_252d is not None
    assert result.expected_return_annual is None
    assert result.target_weight is None


def test_stock_analysis_uses_saved_recommendation_and_current_drift(stock_db, monkeypatch):
    session, user_id, portfolio = stock_db
    points = _points()
    _set_history(monkeypatch, "TCS", points)
    monkeypatch.setattr(
        stock_analysis_service.market_data,
        "get_current_price",
        lambda _ticker: Decimal("100"),
    )
    target = RecommendationSnapshot(
        portfolio_id=portfolio.id,
        created_at=datetime.now(timezone.utc) + timedelta(seconds=1),
        capital=Decimal("10000"),
        universe="NIFTY50",
        universe_as_of=date(2026, 9, 25),
        return_model="ml",
        model_version="hist_gradient_boosting-h20-f12-v1",
        forecast_as_of=date(2026, 9, 25),
        expected_portfolio_return=Decimal("0.1"),
        expected_portfolio_volatility=Decimal("0.12"),
        cash_weight=Decimal("0.9"),
        cash_amount=Decimal("9000"),
        max_position_weight=Decimal("0.2"),
        target_volatility=Decimal("0.15"),
        allocations=[
            {
                "ticker": "TCS",
                "expected_return": "0.11",
                "target_weight": "0.1",
                "amount": "1000",
                "at_position_limit": False,
                "source": "ml",
            }
        ],
        excluded=[],
    )
    session.add(target)
    session.commit()

    result = get_stock_analysis(
        session,
        user_id,
        "TCS",
        portfolio_id=portfolio.id,
        recommendation_id=target.id,
    )

    assert result.recommendation_id == target.id
    assert result.expected_return_annual == Decimal("0.11")
    assert result.expected_return_source == "ml"
    assert result.model_version == "hist_gradient_boosting-h20-f12-v1"
    assert result.target_weight == Decimal("0.1")
    assert result.current_weight is not None


def test_stock_analysis_reports_quote_unavailable_but_keeps_history(stock_db, monkeypatch):
    session, user_id, _ = stock_db
    points = _points()
    _set_history(monkeypatch, "TCS", points)

    def no_quote(_ticker):
        raise MarketDataUnavailableError("TCS", "no current price")

    monkeypatch.setattr(stock_analysis_service.market_data, "get_current_price", no_quote)
    result = get_stock_analysis(session, user_id, "TCS")

    assert result.current_price is None
    assert result.current_quote_available is False
    assert result.latest_close == points[-1].close
    assert result.historical_prices


def test_stock_analysis_rejects_invalid_ticker(stock_db):
    session, user_id, _ = stock_db
    with pytest.raises(HTTPException) as exc_info:
        get_stock_analysis(session, user_id, "BAD/TICKER")
    assert exc_info.value.status_code == 422


def test_stock_analysis_enforces_portfolio_ownership(stock_db, monkeypatch):
    session, _, portfolio = stock_db
    points = _points()
    _set_history(monkeypatch, "TCS", points)
    monkeypatch.setattr(
        stock_analysis_service.market_data,
        "get_current_price",
        lambda _ticker: Decimal("100"),
    )

    with pytest.raises(HTTPException) as exc_info:
        get_stock_analysis(session, uuid4(), "TCS", portfolio_id=portfolio.id)

    assert exc_info.value.status_code == 404


def test_stock_analysis_checks_ownership_before_reading_market_data(stock_db, monkeypatch):
    session, _, portfolio = stock_db
    _set_history(monkeypatch, "TCS", _points())
    monkeypatch.setattr(
        stock_analysis_service.market_data,
        "get_current_price",
        lambda _ticker: Decimal("100"),
    )

    def market_data_must_not_be_requested(*_args, **_kwargs):
        pytest.fail("Ownership must be checked before loading market data")

    monkeypatch.setattr(stock_analysis_service.price_history, "get_price_history", market_data_must_not_be_requested)
    with pytest.raises(HTTPException) as exc_info:
        get_stock_analysis(session, uuid4(), "TCS", portfolio_id=portfolio.id)

    assert exc_info.value.status_code == 404