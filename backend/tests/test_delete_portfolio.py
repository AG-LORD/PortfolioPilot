"""DELETE /portfolios/{id} against the test database, where foreign keys
(including the adopted-plan link) are enforced. The SQLite versions of these
checks live in test_plans.py."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import (
    Holding,
    Portfolio,
    PortfolioSnapshot,
    RebalanceProposal,
    RecommendationSnapshot,
    Transaction,
)

CHILD_MODELS = (Holding, Transaction, PortfolioSnapshot, RecommendationSnapshot, RebalanceProposal)


def _counts(db_session, portfolio_id):
    return {m.__name__: db_session.query(m).filter(m.portfolio_id == portfolio_id).count() for m in CHILD_MODELS}


@pytest.mark.db
def test_delete_portfolio_removes_every_row_with_an_adopted_plan(db_session, test_portfolio):
    from app.api.portfolios import adopt_portfolio_recommendation, delete_own_portfolio

    user_id, portfolio = test_portfolio
    snapshot = RecommendationSnapshot(
        portfolio_id=portfolio.id,
        capital=Decimal("50000"),
        universe="CUSTOM",
        universe_as_of=None,
        return_model="historical",
        expected_portfolio_return=Decimal("0.1"),
        expected_portfolio_volatility=Decimal("0.1"),
        cash_weight=Decimal("1"),
        cash_amount=Decimal("50000"),
        max_position_weight=Decimal("0.1"),
        target_volatility=Decimal("0.15"),
        allocations=[],
        excluded=[],
        not_selected=[],
    )
    db_session.add(snapshot)
    db_session.commit()
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            Holding(portfolio_id=portfolio.id, ticker="ZZTEST_DEL", quantity=Decimal("1"), average_cost=Decimal("1")),
            Transaction(
                portfolio_id=portfolio.id,
                ticker="ZZTEST_DEL",
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("1"),
                fees=Decimal("0"),
                occurred_at=now,
                source="manual",
            ),
            PortfolioSnapshot(
                portfolio_id=portfolio.id,
                snapshot_date=now,
                total_value=Decimal("50000"),
                cash_balance=Decimal("49999"),
                invested_value=Decimal("1"),
            ),
            RebalanceProposal(
                portfolio_id=portfolio.id,
                recommendation_id=snapshot.id,
                state_fingerprint="x",
                portfolio_value=Decimal("50000"),
                cash_before=Decimal("49999"),
                projected_cash=Decimal("49999"),
                buy_total=Decimal("0"),
                sell_total=Decimal("0"),
                estimated_fees=Decimal("0"),
                fee_assumption="none",
                trades=[],
                resulting_weights=[],
            ),
        ]
    )
    db_session.commit()
    adopt_portfolio_recommendation(portfolio.id, snapshot.id, user_id=user_id, db=db_session)

    with pytest.raises(HTTPException) as exc_info:
        delete_own_portfolio(portfolio.id, user_id=uuid4(), db=db_session)
    assert exc_info.value.status_code == 404
    assert set(_counts(db_session, portfolio.id).values()) == {1}

    assert delete_own_portfolio(portfolio.id, user_id=user_id, db=db_session).status_code == 204
    assert db_session.get(Portfolio, portfolio.id) is None
    assert set(_counts(db_session, portfolio.id).values()) == {0}
