"""Phase 1 plan workflow: not_selected reasons, sectors, adopting a plan, drift
and rebalancing against the adopted plan, and atomic batch trades.

Runs on in-memory SQLite (no test database needed), like test_rebalancing."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.portfolios import (
    adopt_portfolio_recommendation,
    delete_own_portfolio,
    create_transaction_batch,
    read_portfolio_recommendation,
    read_portfolios_overview,
)
from app.database import Base
from app.models import (
    Holding,
    Portfolio,
    PortfolioSnapshot,
    RebalanceProposal,
    RecommendationSnapshot,
    RiskProfile,
    Transaction,
    UserProfile,
)
from app.schemas.transaction import BatchTradeItem, BatchTradeRequest
from app.services import drift as drift_service
from app.services import rebalancing as rebalance_service
from app.services.drift import get_portfolio_drift
from app.services.optimization import TargetAllocationResult, TargetWeight
from app.services.rebalancing import create_rebalance_proposal
from app.services.recommendation import (
    NEGATIVE_ESTIMATE,
    POSITION_LIMIT,
    RISK_LIMIT,
    RISK_TRADEOFF,
    SECTOR_LIMIT,
    persist_recommendation_snapshot,
    size_allocation,
)
from app.services.sectors import get_sector, load_sectors


@pytest.fixture
def plan_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def register_now_function(connection, _record):
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user_id = uuid4()
    session.add(UserProfile(id=user_id))
    risk_profile = RiskProfile(
        user_id=user_id,
        score=Decimal("50"),
        category="moderate",
        max_position_weight=Decimal("0.5"),
        max_sector_weight=Decimal("0.6"),
        drift_threshold=Decimal("0.05"),
        target_volatility=Decimal("0.15"),
    )
    session.add(risk_profile)
    session.flush()
    portfolios = []
    for name in ("Mine", "Other"):
        portfolio = Portfolio(
            user_id=user_id,
            risk_profile_id=risk_profile.id,
            name=name,
            purpose=None,
            base_currency="INR",
            initial_capital=Decimal("1000"),
            cash_balance=Decimal("1000"),
        )
        session.add(portfolio)
        portfolios.append(portfolio)
    session.commit()
    yield session, user_id, portfolios[0], portfolios[1]
    session.close()
    engine.dispose()


def _add_snapshot(session, portfolio, allocations, cash_weight, created_at, not_selected=None):
    snapshot = RecommendationSnapshot(
        portfolio_id=portfolio.id,
        created_at=created_at,
        capital=Decimal("1000"),
        universe="CUSTOM",
        universe_as_of=None,
        return_model="historical",
        model_version=None,
        forecast_as_of=None,
        expected_portfolio_return=Decimal("0.1"),
        expected_portfolio_volatility=Decimal("0.1"),
        cash_weight=cash_weight,
        cash_amount=Decimal("0"),
        max_position_weight=Decimal("0.5"),
        target_volatility=Decimal("0.15"),
        allocations=allocations,
        excluded=[],
        not_selected=not_selected,
    )
    session.add(snapshot)
    session.commit()
    return snapshot


def _alloc(ticker, weight):
    return {
        "ticker": ticker,
        "expected_return": "0.1",
        "target_weight": weight,
        "amount": "0",
        "at_position_limit": False,
        "source": "historical",
    }


def _fixed_price(monkeypatch, price=Decimal("100")):
    monkeypatch.setattr(drift_service.market_data, "get_current_price", lambda _t: price)
    monkeypatch.setattr(rebalance_service.market_data, "get_current_price", lambda _t: price)


# --- not_selected and sectors (pure) -------------------------------------------


def test_size_allocation_lists_zero_weight_tickers_with_reasons():
    target = TargetAllocationResult(
        allocations=[
            TargetWeight("INFY", Decimal("0.4"), Decimal("0.12"), Decimal("0.07"), "IT"),
            TargetWeight("TCS", Decimal("0"), Decimal("-0.03"), Decimal("0.01"), "IT"),
            TargetWeight("ITC", Decimal("0"), Decimal("0"), Decimal("0.02"), "FMCG"),
            TargetWeight("ZZNOSECTOR", Decimal("0"), Decimal("0.05"), Decimal("0.04"), "ZZNOSECTOR (no sector)"),
            TargetWeight("HCLTECH", Decimal("0"), Decimal("0.06"), Decimal("0.045"), "IT"),
        ],
        cash_weight=Decimal("0.6"),
        binding_sectors={"IT"},
    )
    sized = size_allocation(
        target,
        [Decimal("0.12"), Decimal("-0.03"), Decimal("0"), Decimal("0.05"), Decimal("0.06")],
        [[Decimal("0.04") if i == j else Decimal("0") for j in range(5)] for i in range(5)],
        Decimal("1000"),
        Decimal("0.4"),
        sources={"TCS": "ml"},
    )

    assert [a.ticker for a in sized.allocations] == ["INFY"]
    assert sized.allocations[0].sector == "IT"
    reasons = {item.ticker: item.reason for item in sized.not_selected}
    # Negative beats sector: TCS is in the binding IT sector but is expected to fall.
    assert reasons == {
        "TCS": NEGATIVE_ESTIMATE,
        "ITC": NEGATIVE_ESTIMATE,
        "ZZNOSECTOR": RISK_TRADEOFF,
        "HCLTECH": SECTOR_LIMIT,
    }
    # INFY sits at the 0.4 position cap, which takes precedence over its sector cap.
    assert sized.allocations[0].limit_reason == POSITION_LIMIT
    assert sized.allocations[0].expected_return == Decimal("0.12")
    assert sized.allocations[0].expected_return_used == Decimal("0.07")
    tcs = next(item for item in sized.not_selected if item.ticker == "TCS")
    assert (tcs.source, tcs.expected_return, tcs.sector) == ("ml", Decimal("-0.03"), "IT")
    assert next(item for item in sized.not_selected if item.ticker == "ZZNOSECTOR").sector is None


def test_sectors_lookup_is_case_insensitive_and_unknown_is_none():
    assert load_sectors()["HDFCBANK"] == "Banking"
    assert get_sector("hdfcbank") == "Banking"
    assert get_sector("ZZTEST_UNKNOWN") is None


# --- persisted not_selected ------------------------------------------------------


def test_saved_recommendation_returns_not_selected_and_old_snapshots_return_null(plan_db):
    session, user_id, portfolio, _ = plan_db
    now = datetime.now(timezone.utc)
    new = _add_snapshot(
        session,
        portfolio,
        [_alloc("INFY", "0.5")],
        Decimal("0.5"),
        now,
        not_selected=[{"ticker": "TCS", "expected_return": "-0.02", "source": "ml", "reason": NEGATIVE_ESTIMATE}],
    )
    old = _add_snapshot(session, portfolio, [_alloc("INFY", "0.5")], Decimal("0.5"), now, not_selected=None)

    read = read_portfolio_recommendation(portfolio.id, new.id, user_id=user_id, db=session)
    [item] = read.not_selected
    assert (item.ticker, item.sector, item.reason, item.source) == ("TCS", "IT", "negative_estimate", "ml")
    assert item.expected_return == Decimal("-0.02")
    assert read.allocations[0].sector == "IT"

    # Older snapshots: unknown (null), not "nothing was left out".
    assert read_portfolio_recommendation(portfolio.id, old.id, user_id=user_id, db=session).not_selected is None


def test_persist_recommendation_snapshot_stores_not_selected(plan_db):
    from app.services.recommendation import (
        NotSelectedTicker,
        Recommendation,
        RecommendationConstraints,
    )

    session, _, portfolio, _ = plan_db
    recommendation = Recommendation(
        universe="CUSTOM",
        universe_as_of=None,
        return_model="historical",
        capital=Decimal("1000"),
        allocations=[],
        cash_weight=Decimal("1"),
        cash_amount=Decimal("1000"),
        expected_portfolio_return=Decimal("0"),
        expected_portfolio_volatility=Decimal("0"),
        constraints=RecommendationConstraints(Decimal("0.5"), Decimal("0.15")),
        excluded=[],
        not_selected=[NotSelectedTicker("TCS", Decimal("0.01"), "historical", RISK_LIMIT, "IT")],
    )
    snapshot = persist_recommendation_snapshot(session, portfolio.id, recommendation)
    assert snapshot.not_selected == [
        {"ticker": "TCS", "expected_return": "0.01", "source": "historical", "reason": "risk_limit", "expected_return_used": None}
    ]


# --- adopting a plan -------------------------------------------------------------


def test_adopt_sets_plan_without_touching_updated_at(plan_db):
    session, user_id, portfolio, _ = plan_db
    snapshot = _add_snapshot(session, portfolio, [_alloc("A", "0.5")], Decimal("0.5"), datetime.now(timezone.utc))
    updated_before = session.get(Portfolio, portfolio.id).updated_at

    result = adopt_portfolio_recommendation(portfolio.id, snapshot.id, user_id=user_id, db=session)

    assert result.adopted_recommendation_id == snapshot.id
    assert result.adopted_at is not None
    assert result.updated_at == updated_before


def test_adopt_rejects_other_users_and_foreign_or_unknown_recommendations(plan_db):
    session, user_id, portfolio, other = plan_db
    foreign = _add_snapshot(session, other, [_alloc("A", "0.5")], Decimal("0.5"), datetime.now(timezone.utc))
    own = _add_snapshot(session, portfolio, [_alloc("A", "0.5")], Decimal("0.5"), datetime.now(timezone.utc))

    for rid, uid in ((foreign.id, user_id), (uuid4(), user_id), (own.id, uuid4())):
        with pytest.raises(HTTPException) as exc_info:
            adopt_portfolio_recommendation(portfolio.id, rid, user_id=uid, db=session)
        assert exc_info.value.status_code == 404
    assert session.get(Portfolio, portfolio.id).adopted_recommendation_id is None


def test_drift_and_proposals_use_the_adopted_plan_not_the_latest(plan_db, monkeypatch):
    session, user_id, portfolio, _ = plan_db
    _fixed_price(monkeypatch)
    now = datetime.now(timezone.utc)
    adopted = _add_snapshot(session, portfolio, [_alloc("A", "0.5")], Decimal("0.5"), now + timedelta(seconds=1))
    latest = _add_snapshot(session, portfolio, [_alloc("B", "0.3")], Decimal("0.7"), now + timedelta(seconds=2))

    drift = get_portfolio_drift(session, user_id, portfolio.id)
    assert drift.target_recommendation_id == latest.id

    adopt_portfolio_recommendation(portfolio.id, adopted.id, user_id=user_id, db=session)
    drift = get_portfolio_drift(session, user_id, portfolio.id)
    assert drift.target_recommendation_id == adopted.id
    assert {p.ticker: p.target_weight for p in drift.positions}["A"] == Decimal("0.5")

    proposal = create_rebalance_proposal(session, user_id, portfolio.id)
    assert proposal.recommendation_id == adopted.id
    assert [(t.side, t.ticker, t.quantity) for t in proposal.trades] == [("BUY", "A", 5)]


def test_adopted_plan_stays_current_after_recording_its_orders(plan_db, monkeypatch):
    session, user_id, portfolio, _ = plan_db
    _fixed_price(monkeypatch)
    snapshot = _add_snapshot(
        session, portfolio, [_alloc("A", "0.3"), _alloc("B", "0.3")], Decimal("0.4"), datetime.now(timezone.utc)
    )
    adopt_portfolio_recommendation(portfolio.id, snapshot.id, user_id=user_id, db=session)

    create_transaction_batch(
        portfolio.id,
        [BatchTradeItem(side="BUY", ticker="A", quantity=Decimal("3"), price=Decimal("100"))],
        user_id=user_id,
        db=session,
    )

    assert get_portfolio_drift(session, user_id, portfolio.id).target_status == "current"
    remaining = create_rebalance_proposal(session, user_id, portfolio.id)
    assert [(t.side, t.ticker, t.quantity) for t in remaining.trades] == [("BUY", "B", 3)]


# --- batch trades ----------------------------------------------------------------


def test_batch_records_every_row(plan_db):
    session, user_id, portfolio, _ = plan_db

    rows = create_transaction_batch(
        portfolio.id,
        [
            BatchTradeItem(side="BUY", ticker="a", quantity=Decimal("2"), price=Decimal("100"), fees=Decimal("1")),
            BatchTradeItem(side="BUY", ticker="B", quantity=Decimal("3"), price=Decimal("50")),
            BatchTradeItem(side="SELL", ticker="A", quantity=Decimal("1"), price=Decimal("110")),
        ],
        user_id=user_id,
        db=session,
    )

    assert [(r.transaction_type, r.ticker) for r in rows] == [("BUY", "A"), ("BUY", "B"), ("SELL", "A")]
    holdings = {h.ticker: h.quantity for h in session.query(Holding).filter(Holding.portfolio_id == portfolio.id)}
    assert holdings == {"A": Decimal("1"), "B": Decimal("3")}
    assert session.get(Portfolio, portfolio.id).cash_balance == Decimal("1000") - 201 - 150 + 110


def test_batch_rolls_back_everything_when_the_second_row_fails(plan_db):
    session, user_id, portfolio, _ = plan_db

    with pytest.raises(HTTPException) as exc_info:
        create_transaction_batch(
            portfolio.id,
            [
                BatchTradeItem(side="BUY", ticker="A", quantity=Decimal("2"), price=Decimal("100")),
                BatchTradeItem(side="BUY", ticker="B", quantity=Decimal("100"), price=Decimal("100")),
            ],
            user_id=user_id,
            db=session,
        )

    assert exc_info.value.status_code == 422
    assert "Row 2" in exc_info.value.detail and "Insufficient cash balance" in exc_info.value.detail
    assert session.query(Holding).filter(Holding.portfolio_id == portfolio.id).count() == 0
    assert session.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).count() == 0
    assert session.get(Portfolio, portfolio.id).cash_balance == Decimal("1000")


def test_batch_is_404_for_another_users_portfolio(plan_db):
    session, _, portfolio, _ = plan_db
    with pytest.raises(HTTPException) as exc_info:
        create_transaction_batch(
            portfolio.id,
            [BatchTradeItem(side="BUY", ticker="A", quantity=Decimal("1"), price=Decimal("1"))],
            user_id=uuid4(),
            db=session,
        )
    assert exc_info.value.status_code == 404
    assert session.query(Transaction).count() == 0


def test_batch_request_accepts_1_to_50_trades():
    adapter = TypeAdapter(BatchTradeRequest)
    row = {"side": "BUY", "ticker": "A", "quantity": "1", "price": "1"}
    assert len(adapter.validate_python([row] * 50)) == 50
    for rows in ([], [row] * 51):
        with pytest.raises(ValidationError):
            adapter.validate_python(rows)
    with pytest.raises(ValidationError):
        adapter.validate_python([{**row, "side": "DEPOSIT"}])


# --- overview --------------------------------------------------------------------


def test_overview_exposes_adopted_plan_and_sparkline(plan_db):
    session, user_id, portfolio, other = plan_db
    snapshot = _add_snapshot(session, portfolio, [], Decimal("1"), datetime.now(timezone.utc))
    adopt_portfolio_recommendation(portfolio.id, snapshot.id, user_id=user_id, db=session)
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    for day, value in enumerate(["1000", "1010", "990"]):
        session.add(
            PortfolioSnapshot(
                portfolio_id=portfolio.id,
                snapshot_date=start + timedelta(days=day),
                total_value=Decimal(value),
                cash_balance=Decimal(value),
                invested_value=Decimal("0"),
            )
        )
    session.add(
        PortfolioSnapshot(
            portfolio_id=other.id,
            snapshot_date=start,
            total_value=Decimal("1000"),
            cash_balance=Decimal("1000"),
            invested_value=Decimal("0"),
        )
    )
    session.commit()

    items = {item.id: item for item in read_portfolios_overview(user_id=user_id, db=session).portfolios}

    assert items[portfolio.id].adopted_recommendation_id == snapshot.id
    assert items[portfolio.id].adopted_at is not None
    assert items[portfolio.id].sparkline == [Decimal("1000"), Decimal("1010"), Decimal("990")]
    assert items[other.id].adopted_recommendation_id is None
    assert items[other.id].sparkline == []


# --- deleting a portfolio ---------------------------------------------------------


def _fill_portfolio(session, portfolio):
    snapshot = _add_snapshot(session, portfolio, [_alloc("A", "0.5")], Decimal("0.5"), datetime.now(timezone.utc))
    session.add_all(
        [
            Holding(portfolio_id=portfolio.id, ticker="A", quantity=Decimal("1"), average_cost=Decimal("10")),
            Transaction(
                portfolio_id=portfolio.id,
                ticker="A",
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("10"),
                fees=Decimal("0"),
                occurred_at=datetime.now(timezone.utc),
                source="manual",
            ),
            PortfolioSnapshot(
                portfolio_id=portfolio.id,
                snapshot_date=datetime.now(timezone.utc),
                total_value=Decimal("1000"),
                cash_balance=Decimal("990"),
                invested_value=Decimal("10"),
            ),
            RebalanceProposal(
                portfolio_id=portfolio.id,
                recommendation_id=snapshot.id,
                state_fingerprint="x",
                portfolio_value=Decimal("1000"),
                cash_before=Decimal("990"),
                projected_cash=Decimal("990"),
                buy_total=Decimal("0"),
                sell_total=Decimal("0"),
                estimated_fees=Decimal("0"),
                fee_assumption="none",
                trades=[],
                resulting_weights=[],
            ),
        ]
    )
    session.commit()
    adopt_portfolio_recommendation(portfolio.id, snapshot.id, user_id=portfolio.user_id, db=session)


def _row_counts(session, portfolio_id):
    return {
        model.__name__: session.query(model).filter(model.portfolio_id == portfolio_id).count()
        for model in (Holding, Transaction, PortfolioSnapshot, RecommendationSnapshot, RebalanceProposal)
    }


def test_delete_removes_the_portfolio_and_all_its_rows_only(plan_db):
    session, user_id, portfolio, other = plan_db
    _fill_portfolio(session, portfolio)
    _fill_portfolio(session, other)
    other_before = _row_counts(session, other.id)

    response = delete_own_portfolio(portfolio.id, user_id=user_id, db=session)

    assert response.status_code == 204
    assert session.get(Portfolio, portfolio.id) is None
    assert set(_row_counts(session, portfolio.id).values()) == {0}
    assert session.get(Portfolio, other.id) is not None
    assert _row_counts(session, other.id) == other_before
    assert session.get(Portfolio, other.id).adopted_recommendation_id is not None


def test_delete_is_404_for_another_users_portfolio(plan_db):
    session, _, portfolio, _ = plan_db
    _fill_portfolio(session, portfolio)
    before = _row_counts(session, portfolio.id)

    with pytest.raises(HTTPException) as exc_info:
        delete_own_portfolio(portfolio.id, user_id=uuid4(), db=session)

    assert exc_info.value.status_code == 404
    assert session.get(Portfolio, portfolio.id) is not None
    assert _row_counts(session, portfolio.id) == before


def test_overview_total_deposited_adds_later_deposits(plan_db):
    from app.services.portfolios import add_capital

    session, user_id, portfolio, other = plan_db
    add_capital(session, user_id, portfolio.id, Decimal("250.50"))

    items = {item.id: item for item in read_portfolios_overview(user_id=user_id, db=session).portfolios}

    assert items[portfolio.id].total_deposited == Decimal("1250.50")
    assert items[other.id].total_deposited == Decimal("1000")


def test_snapshots_saved_before_mean_variance_still_read(plan_db):
    session, user_id, portfolio, _ = plan_db
    # Allocation without expected_return_used / limit_reason, and the retired "risk_limit" reason.
    old = _add_snapshot(
        session,
        portfolio,
        [_alloc("INFY", "0.5")],
        Decimal("0.5"),
        datetime.now(timezone.utc),
        not_selected=[{"ticker": "TCS", "expected_return": "0.01", "source": "historical", "reason": "risk_limit"}],
    )

    read = read_portfolio_recommendation(portfolio.id, old.id, user_id=user_id, db=session)

    [allocation] = read.allocations
    assert (allocation.expected_return_used, allocation.limit_reason) == (None, None)
    [item] = read.not_selected
    assert (item.reason, item.expected_return_used) == ("risk_limit", None)
    # The sector cap comes from the portfolio's risk profile.
    assert read.constraints.max_sector_weight == Decimal("0.6")
