from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.models import Holding, Portfolio, RebalanceProposal, Transaction
from app.dependencies import get_current_user_id, get_db
from app.main import app
from app.schemas.rebalance import RebalanceExecutionRequest
from app.services import rebalancing as rebalance_service
from app.services.market_data import MarketDataUnavailableError
from app.services.rebalance_execution import (
    RebalanceExecutionConflict,
    execute_rebalance_proposal,
)
from app.services.rebalancing import create_rebalance_proposal
from test_rebalancing import _add_target, rebalance_db


def _stable_price(monkeypatch, prices):
    monkeypatch.setattr(
        rebalance_service.market_data,
        "get_current_price",
        lambda ticker: prices[ticker],
    )
    import app.services.rebalance_execution as execution_service

    monkeypatch.setattr(
        execution_service.market_data,
        "get_current_price",
        lambda ticker: prices[ticker],
    )


def test_execution_request_requires_explicit_confirmation():
    with pytest.raises(ValidationError):
        RebalanceExecutionRequest(confirm=False)


def test_api_rebalance_requires_confirmation_and_executes_after_confirm(rebalance_db, monkeypatch):
    session, user_id, portfolio = rebalance_db
    session.add(
        Holding(
            portfolio_id=portfolio.id,
            ticker="A",
            quantity=Decimal("4"),
            average_cost=Decimal("90"),
        )
    )
    _add_target(
        session,
        portfolio,
        [
            {"ticker": "A", "target_weight": "0.2"},
            {"ticker": "B", "target_weight": "0.5"},
        ],
    )
    _stable_price(monkeypatch, {"A": Decimal("100"), "B": Decimal("100")})

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    try:
        with TestClient(app) as client:
            proposal_response = client.post(
                f"/portfolios/{portfolio.id}/rebalance-proposals",
                json={},
            )
            assert proposal_response.status_code == 201, proposal_response.text
            proposal_id = proposal_response.json()["id"]
            refused = client.post(
                f"/portfolios/{portfolio.id}/rebalance-proposals/{proposal_id}/execute",
                json={"confirm": False},
            )
            assert refused.status_code == 422
            assert session.get(RebalanceProposal, UUID(proposal_id)).status == "PENDING"

            executed = client.post(
                f"/portfolios/{portfolio.id}/rebalance-proposals/{proposal_id}/execute",
                json={"confirm": True},
            )
            assert executed.status_code == 200, executed.text
            assert executed.json()["status"] == "EXECUTED"
            assert executed.json()["cash_balance"] == "300.0000"
    finally:
        app.dependency_overrides.clear()

    assert session.get(RebalanceProposal, UUID(proposal_id)).status == "EXECUTED"
    assert session.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).count() == 2


def test_successful_execution_updates_holdings_cash_and_transactions(rebalance_db, monkeypatch):
    session, user_id, portfolio = rebalance_db
    session.add(
        Holding(
            portfolio_id=portfolio.id,
            ticker="A",
            quantity=Decimal("4"),
            average_cost=Decimal("90"),
        )
    )
    _add_target(
        session,
        portfolio,
        [
            {"ticker": "A", "target_weight": "0.2"},
            {"ticker": "B", "target_weight": "0.5"},
        ],
    )
    _stable_price(monkeypatch, {"A": Decimal("100"), "B": Decimal("100")})
    proposal = create_rebalance_proposal(session, user_id, portfolio.id)

    result = execute_rebalance_proposal(session, user_id, portfolio.id, proposal.id)

    assert result.status == "EXECUTED"
    assert result.cash_balance == Decimal("300")
    assert session.get(RebalanceProposal, proposal.id).status == "EXECUTED"
    holdings = {
        holding.ticker: holding
        for holding in session.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()
    }
    assert holdings["A"].quantity == Decimal("2")
    assert holdings["B"].quantity == Decimal("5")
    transactions = session.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).all()
    assert {(txn.ticker, txn.transaction_type, txn.source, txn.quantity) for txn in transactions} == {
        ("A", "SELL", "rebalance", Decimal("2")),
        ("B", "BUY", "rebalance", Decimal("5")),
    }
    assert len(result.transaction_ids) == 2


def test_duplicate_execution_is_rejected_without_second_trade(rebalance_db, monkeypatch):
    session, user_id, portfolio = rebalance_db
    _add_target(session, portfolio, [{"ticker": "B", "target_weight": "0.5"}])
    _stable_price(monkeypatch, {"B": Decimal("100")})
    proposal = create_rebalance_proposal(session, user_id, portfolio.id)
    result = execute_rebalance_proposal(session, user_id, portfolio.id, proposal.id)

    with pytest.raises(RebalanceExecutionConflict, match="no longer pending"):
        execute_rebalance_proposal(session, user_id, portfolio.id, proposal.id)

    assert session.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).count() == len(result.transaction_ids)


def test_stale_proposal_expires_without_portfolio_mutation(rebalance_db, monkeypatch):
    session, user_id, portfolio = rebalance_db
    _add_target(session, portfolio, [{"ticker": "B", "target_weight": "0.5"}])
    _stable_price(monkeypatch, {"B": Decimal("100")})
    proposal = create_rebalance_proposal(session, user_id, portfolio.id)
    cash_before = portfolio.cash_balance
    portfolio.cash_balance += Decimal("1")
    session.commit()

    with pytest.raises(RebalanceExecutionConflict, match="state or prices changed"):
        execute_rebalance_proposal(session, user_id, portfolio.id, proposal.id)

    assert session.get(RebalanceProposal, proposal.id).status == "EXPIRED"
    assert session.get(Portfolio, portfolio.id).cash_balance == cash_before + Decimal("1")
    assert session.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).count() == 0


def test_insufficient_cash_rejects_entire_execution(rebalance_db, monkeypatch):
    session, user_id, portfolio = rebalance_db
    portfolio.cash_balance = Decimal("100")
    _add_target(
        session,
        portfolio,
        [{"ticker": "B", "target_weight": "2.0"}],
        cash_weight=Decimal("0"),
    )
    _stable_price(monkeypatch, {"B": Decimal("30")})
    proposal = create_rebalance_proposal(session, user_id, portfolio.id)
    stored_proposal = session.get(RebalanceProposal, proposal.id)
    stored_proposal.trades = [
        {
            **proposal.trades[0].model_dump(mode="json"),
            "quantity": 4,
            "estimated_gross_amount": "120",
            "estimated_net_amount": "120",
        }
    ]
    session.commit()

    with pytest.raises(RebalanceExecutionConflict, match="exceeds available cash"):
        execute_rebalance_proposal(session, user_id, portfolio.id, proposal.id)

    session.rollback()
    assert session.get(Portfolio, portfolio.id).cash_balance == Decimal("100")
    assert session.query(Holding).filter(Holding.portfolio_id == portfolio.id).count() == 0
    assert session.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).count() == 0


def test_invalid_quantity_rejects_execution(rebalance_db, monkeypatch):
    session, user_id, portfolio = rebalance_db
    _add_target(session, portfolio, [{"ticker": "B", "target_weight": "0.5"}])
    _stable_price(monkeypatch, {"B": Decimal("100")})
    proposal = create_rebalance_proposal(session, user_id, portfolio.id)
    stored_proposal = session.get(RebalanceProposal, proposal.id)
    stored_proposal.trades = [{**proposal.trades[0].model_dump(mode="json"), "quantity": 0}]
    session.commit()

    with pytest.raises(RebalanceExecutionConflict, match="positive whole shares"):
        execute_rebalance_proposal(session, user_id, portfolio.id, proposal.id)

    assert session.get(Portfolio, portfolio.id).cash_balance == Decimal("600")
    assert session.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).count() == 0


def test_unauthorized_execution_is_rejected(rebalance_db, monkeypatch):
    session, user_id, portfolio = rebalance_db
    _add_target(session, portfolio, [{"ticker": "B", "target_weight": "0.5"}])
    _stable_price(monkeypatch, {"B": Decimal("100")})
    proposal = create_rebalance_proposal(session, user_id, portfolio.id)

    with pytest.raises(HTTPException) as exc_info:
        execute_rebalance_proposal(session, uuid4(), portfolio.id, proposal.id)

    assert exc_info.value.status_code == 404
    assert session.get(Portfolio, portfolio.id).cash_balance == Decimal("600")
    assert session.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).count() == 0


def test_database_failure_rolls_back_holdings_cash_and_transactions(rebalance_db, monkeypatch):
    session, user_id, portfolio = rebalance_db
    session.add(
        Holding(
            portfolio_id=portfolio.id,
            ticker="A",
            quantity=Decimal("4"),
            average_cost=Decimal("90"),
        )
    )
    _add_target(
        session,
        portfolio,
        [
            {"ticker": "A", "target_weight": "0.2"},
            {"ticker": "B", "target_weight": "0.5"},
        ],
    )
    _stable_price(monkeypatch, {"A": Decimal("100"), "B": Decimal("100")})
    proposal = create_rebalance_proposal(session, user_id, portfolio.id)
    cash_before = portfolio.cash_balance
    holdings_before = [(h.ticker, h.quantity) for h in session.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()]

    def fail_commit():
        raise SQLAlchemyError("simulated commit failure")

    monkeypatch.setattr(session, "commit", fail_commit)
    with pytest.raises(SQLAlchemyError, match="simulated commit failure"):
        execute_rebalance_proposal(session, user_id, portfolio.id, proposal.id)
    monkeypatch.undo()
    session.expire_all()

    assert session.get(Portfolio, portfolio.id).cash_balance == cash_before
    assert sorted((h.ticker, h.quantity) for h in session.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()) == sorted(holdings_before)
    assert session.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).count() == 0
    assert session.get(RebalanceProposal, proposal.id).status == "PENDING"