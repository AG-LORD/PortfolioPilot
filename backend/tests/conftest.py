# The test-database guard lives in backend/conftest.py, which pytest loads
# before this file and before any app import.
import uuid
from decimal import Decimal

import pytest
from price_fakes import TEST_TICKER_PREFIX, FakeMarket

from app.database import SessionLocal
from app.models import (
    DailyPrice,
    Holding,
    Portfolio,
    PortfolioSnapshot,
    PriceCacheCoverage,
    RiskProfile,
    Transaction,
    UserProfile,
)
from app.services import market_data


def _purge_test_price_cache(session):
    session.query(DailyPrice).filter(
        DailyPrice.ticker.startswith(TEST_TICKER_PREFIX, autoescape=True)
    ).delete(synchronize_session=False)
    session.query(PriceCacheCoverage).filter(
        PriceCacheCoverage.ticker.startswith(TEST_TICKER_PREFIX, autoescape=True)
    ).delete(synchronize_session=False)
    session.commit()


@pytest.fixture
def fake_market(db_session, monkeypatch):
    _purge_test_price_cache(db_session)
    market = FakeMarket()
    monkeypatch.setattr(market_data, "download_history_batch", market.download)
    yield market
    db_session.rollback()
    _purge_test_price_cache(db_session)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_portfolio(db_session):
    user_id = uuid.uuid4()
    db_session.add(UserProfile(id=user_id))
    db_session.commit()

    risk_profile = RiskProfile(
        user_id=user_id,
        score=Decimal("50"),
        category="moderate",
        max_position_weight=Decimal("0.1"),
        max_sector_weight=Decimal("0.25"),
        drift_threshold=Decimal("0.05"),
        target_volatility=Decimal("0.15"),
    )
    db_session.add(risk_profile)
    db_session.commit()
    db_session.refresh(risk_profile)

    portfolio = Portfolio(
        user_id=user_id,
        risk_profile_id=risk_profile.id,
        name="Test Portfolio",
        purpose=None,
        base_currency="INR",
        initial_capital=Decimal("100000"),
        cash_balance=Decimal("50000"),
    )
    db_session.add(portfolio)
    db_session.commit()
    db_session.refresh(portfolio)

    yield user_id, portfolio

    db_session.rollback()
    db_session.query(PortfolioSnapshot).filter(
        PortfolioSnapshot.portfolio_id == portfolio.id
    ).delete()
    db_session.query(Transaction).filter(
        Transaction.portfolio_id == portfolio.id
    ).delete()
    db_session.query(Holding).filter(Holding.portfolio_id == portfolio.id).delete()
    db_session.query(Portfolio).filter(Portfolio.id == portfolio.id).delete()
    db_session.query(RiskProfile).filter(RiskProfile.id == risk_profile.id).delete()
    db_session.query(UserProfile).filter(UserProfile.id == user_id).delete()
    db_session.commit()
