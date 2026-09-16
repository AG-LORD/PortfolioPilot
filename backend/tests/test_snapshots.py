from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import Holding
from app.services.market_data import MarketDataUnavailableError
from app.services.snapshots import _market_snapshot_date, create_portfolio_snapshot


def test_market_snapshot_date_uses_ist_calendar_day_not_utc():
    # 17 Sep 2026 01:00 IST == 16 Sep 2026 19:30 UTC.
    # This must resolve to the IST date, not the UTC date.
    utc_instant = datetime(2026, 9, 16, 19, 30, tzinfo=timezone.utc)

    result = _market_snapshot_date(utc_instant)

    assert result.date() == date(2026, 9, 17)


def test_market_snapshot_date_just_before_ist_midnight_stays_previous_day():
    # 16 Sep 2026 23:59 IST == 16 Sep 2026 18:29 UTC.
    utc_instant = datetime(2026, 9, 16, 18, 29, tzinfo=timezone.utc)

    result = _market_snapshot_date(utc_instant)

    assert result.date() == date(2026, 9, 16)
from app.services.valuation import get_portfolio_valuation


@patch("app.services.market_data.get_current_price")
def test_snapshot_creation_first_snapshot_has_no_daily_return(mock_price, db_session, test_portfolio):
    user_id, portfolio = test_portfolio
    mock_price.return_value = Decimal("100")

    snapshot = create_portfolio_snapshot(db_session, user_id, portfolio.id)

    assert snapshot.daily_return is None
    expected_cumulative = (snapshot.total_value - portfolio.initial_capital) / portfolio.initial_capital
    assert snapshot.cumulative_return == expected_cumulative


@patch("app.services.market_data.get_current_price")
def test_duplicate_snapshot_same_day_rejected(mock_price, db_session, test_portfolio):
    user_id, portfolio = test_portfolio
    mock_price.return_value = Decimal("100")

    create_portfolio_snapshot(db_session, user_id, portfolio.id)

    with pytest.raises(HTTPException) as exc_info:
        create_portfolio_snapshot(db_session, user_id, portfolio.id)

    assert exc_info.value.status_code == 409


def test_valuation_unauthorized_access_raises_404(db_session, test_portfolio):
    _, portfolio = test_portfolio

    with pytest.raises(HTTPException) as exc_info:
        get_portfolio_valuation(db_session, uuid4(), portfolio.id)

    assert exc_info.value.status_code == 404


def test_snapshot_unauthorized_access_raises_404(db_session, test_portfolio):
    _, portfolio = test_portfolio

    with pytest.raises(HTTPException) as exc_info:
        create_portfolio_snapshot(db_session, uuid4(), portfolio.id)

    assert exc_info.value.status_code == 404


@patch("app.services.market_data.get_current_price")
def test_valuation_fails_entirely_if_any_ticker_unpriced(mock_price, db_session, test_portfolio):
    user_id, portfolio = test_portfolio

    holding = Holding(
        portfolio_id=portfolio.id,
        ticker="FAKETICKER",
        quantity=Decimal("1"),
        average_cost=Decimal("100"),
    )
    db_session.add(holding)
    db_session.commit()

    mock_price.side_effect = MarketDataUnavailableError("FAKETICKER", "no data")

    try:
        with pytest.raises(MarketDataUnavailableError):
            get_portfolio_valuation(db_session, user_id, portfolio.id)
    finally:
        db_session.query(Holding).filter(Holding.id == holding.id).delete()
        db_session.commit()
