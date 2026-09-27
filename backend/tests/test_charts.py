"""Chart series: fixed-weight history preview, snapshot performance vs NIFTY 50,
and the NIFTY 50 benchmark symbol. Pure maths needs no database; the route
tests are db-marked."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

import pandas as pd
import pytest
from fastapi import HTTPException
from price_fakes import make_series

from app.services import market_data
from app.services.charts import fixed_weight_history, performance_series, preview_note
from app.services.market_calendar import MARKET_TIMEZONE
from app.services.market_data import PricePoint


def _points(closes: dict[date, str]) -> list[PricePoint]:
    return [
        PricePoint(date=d, open=Decimal(c), high=Decimal(c), low=Decimal(c), close=Decimal(c), volume=0)
        for d, c in sorted(closes.items())
    ]


D1, D2, D3 = date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)


# --- fixed-weight history (pure) --------------------------------------------------


def test_fixed_weights_compound_daily_with_cash_at_zero():
    prices = {"A": _points({D1: "100", D2: "110", D3: "99"}), "B": _points({D1: "50", D2: "50", D3: "55"})}
    bench = _points({D1: "20000", D2: "20200", D3: "19800"})

    result = fixed_weight_history(
        prices, {"A": Decimal("0.5"), "B": Decimal("0.2")}, Decimal("100000"), bench, D1
    )

    day2 = Decimal("100000") * (1 + Decimal("0.5") * Decimal("0.1"))
    day3 = day2 * (1 + Decimal("0.5") * Decimal("-0.1") + Decimal("0.2") * Decimal("0.1"))
    assert [p.mix for p in result.points] == [
        Decimal("100000.00"),
        day2.quantize(Decimal("0.01")),
        day3.quantize(Decimal("0.01")),
    ]
    assert [p.benchmark for p in result.points] == [Decimal("100000.00"), Decimal("101000.00"), Decimal("99000.00")]
    assert (result.start, result.end, result.late_tickers) == (D1, D3, [])


def test_all_cash_mix_stays_flat():
    bench = _points({D1: "100", D2: "105"})
    result = fixed_weight_history({}, {}, Decimal("5000"), bench, D1)
    assert [p.mix for p in result.points] == [Decimal("5000.00"), Decimal("5000.00")]
    assert result.points[-1].benchmark == Decimal("5250.00")


def test_late_listed_ticker_moves_the_start_to_the_latest_common_date():
    start = date(2025, 1, 1)
    late_start = start + timedelta(days=30)
    days = [start + timedelta(days=i) for i in range(60)]
    prices = {
        "OLD": _points({d: "100" for d in days}),
        "NEW": _points({d: "10" for d in days if d >= late_start}),
    }
    bench = _points({d: "1000" for d in days})

    result = fixed_weight_history(prices, {"OLD": Decimal("0.4"), "NEW": Decimal("0.4")}, Decimal("100"), bench, start)

    assert result.start == late_start
    assert result.late_tickers == ["NEW"]
    note = preview_note("1y", result.late_tickers, result.start)
    assert "NEW" in note and late_start.isoformat() in note
    assert "not a backtest" in note and "not a forecast" in note and "hindsight" in note


def test_only_days_where_every_series_has_a_close_are_used():
    prices = {"A": _points({D1: "100", D3: "120"})}
    bench = _points({D1: "10", D2: "11", D3: "12"})
    result = fixed_weight_history(prices, {"A": Decimal("1")}, Decimal("100"), bench, D1)
    assert [p.date for p in result.points] == [D1, D3]
    assert result.points[-1].mix == Decimal("120.00")


def test_missing_history_is_an_error():
    with pytest.raises(ValueError):
        fixed_weight_history({"A": []}, {"A": Decimal("1")}, Decimal("100"), _points({D1: "1"}), D1)


# --- performance series (pure) --------------------------------------------------


def test_performance_needs_two_snapshots():
    assert performance_series([(D1, Decimal("100"))], _points({D1: "10"})) == []
    assert performance_series([], []) == []


def test_performance_scales_benchmark_to_first_snapshot_and_carries_last_close():
    bench = _points({D1: "200", D3: "220"})  # no close on D2
    points = performance_series([(D1, Decimal("1000")), (D2, Decimal("1010")), (D3, Decimal("1050"))], bench)

    assert [(p.date, p.portfolio, p.benchmark) for p in points] == [
        (D1, Decimal("1000.00"), Decimal("1000.00")),
        (D2, Decimal("1010.00"), Decimal("1000.00")),
        (D3, Decimal("1050.00"), Decimal("1100.00")),
    ]


def test_performance_benchmark_is_null_without_any_close():
    points = performance_series([(D1, Decimal("1")), (D2, Decimal("2"))], [])
    assert [p.benchmark for p in points] == [None, None]


# --- NIFTY 50 benchmark symbol ---------------------------------------------------


def test_benchmark_uses_the_index_symbol_without_ns_suffix():
    assert market_data._to_yfinance_symbol(market_data.NIFTY50_INDEX) == "^NSEI"
    assert market_data._to_yfinance_symbol("infy") == "INFY.NS"


def test_index_rows_without_volume_are_kept(monkeypatch):
    index = pd.to_datetime(["2026-01-05", "2026-01-06"])
    columns = pd.MultiIndex.from_product([["^NSEI", "INFY.NS"], ["Open", "High", "Low", "Close", "Volume"]])
    frame = pd.DataFrame(
        [
            [1.0, 1.0, 1.0, 1.0, float("nan"), 2.0, 2.0, 2.0, 2.0, float("nan")],
            [3.0, 3.0, 3.0, 3.0, float("nan"), 4.0, 4.0, 4.0, 4.0, 10.0],
        ],
        index=index,
        columns=columns,
    )
    monkeypatch.setattr(market_data.yf, "download", lambda *args, **kwargs: frame)

    result = market_data.download_history_batch(
        [market_data.NIFTY50_INDEX, "INFY"], date(2026, 1, 5), date(2026, 1, 7)
    )

    assert [(p.close, p.volume) for p in result[market_data.NIFTY50_INDEX]] == [(Decimal("1.0"), 0), (Decimal("3.0"), 0)]
    # Stocks keep the old rule: a bar without volume is not real data.
    assert [p.close for p in result["INFY"]] == [Decimal("4.0")]


# --- routes (DB) -----------------------------------------------------------------


BENCH = "ZZTEST_NIFTY"


def _snapshot(db_session, portfolio, allocations):
    from app.models import RecommendationSnapshot

    snapshot = RecommendationSnapshot(
        portfolio_id=portfolio.id,
        capital=Decimal("100000"),
        universe="CUSTOM",
        universe_as_of=None,
        return_model="historical",
        expected_portfolio_return=Decimal("0.1"),
        expected_portfolio_volatility=Decimal("0.1"),
        cash_weight=Decimal("0.6"),
        cash_amount=Decimal("60000"),
        max_position_weight=Decimal("0.2"),
        target_volatility=Decimal("0.15"),
        allocations=allocations,
        excluded=[],
    )
    db_session.add(snapshot)
    db_session.commit()
    return snapshot


@pytest.mark.db
def test_history_preview_route_returns_mix_and_benchmark(db_session, test_portfolio, fake_market, monkeypatch):
    from app.api.portfolios import read_recommendation_history_preview

    monkeypatch.setattr(market_data, "NIFTY50_INDEX", BENCH)
    user_id, portfolio = test_portfolio
    fake_market.series = {
        "ZZTEST_HPA": make_series(1, n_days=400),
        "ZZTEST_HPB": make_series(2, n_days=400),
        BENCH: make_series(3, n_days=400),
    }
    snapshot = _snapshot(
        db_session,
        portfolio,
        [{"ticker": "ZZTEST_HPA", "target_weight": "0.2"}, {"ticker": "ZZTEST_HPB", "target_weight": "0.2"}],
    )

    result = read_recommendation_history_preview(portfolio.id, snapshot.id, user_id=user_id, db=db_session)

    assert result.points[0].mix == result.points[0].benchmark == Decimal("100000.00")
    assert len(result.points) > 200
    assert result.start == result.points[0].date and result.end == result.points[-1].date
    assert "not a backtest" in result.note


@pytest.mark.db
def test_chart_routes_hide_other_users_portfolio(db_session, test_portfolio):
    from app.api.portfolios import read_portfolio_performance, read_recommendation_history_preview

    _, portfolio = test_portfolio
    snapshot = _snapshot(db_session, portfolio, [])
    stranger = uuid4()
    for call in (
        lambda: read_recommendation_history_preview(portfolio.id, snapshot.id, user_id=stranger, db=db_session),
        lambda: read_portfolio_performance(portfolio.id, user_id=stranger, db=db_session),
    ):
        with pytest.raises(HTTPException) as exc_info:
            call()
        assert exc_info.value.status_code == 404


@pytest.mark.db
def test_history_preview_is_404_for_another_portfolios_recommendation(db_session, test_portfolio):
    from app.api.portfolios import read_recommendation_history_preview

    user_id, portfolio = test_portfolio
    with pytest.raises(HTTPException) as exc_info:
        read_recommendation_history_preview(portfolio.id, uuid4(), user_id=user_id, db=db_session)
    assert exc_info.value.status_code == 404


@pytest.mark.db
def test_performance_route_scales_benchmark_to_first_snapshot(db_session, test_portfolio, fake_market, monkeypatch):
    from app.api.portfolios import read_portfolio_performance
    from app.models import PortfolioSnapshot

    monkeypatch.setattr(market_data, "NIFTY50_INDEX", BENCH)
    user_id, portfolio = test_portfolio
    assert read_portfolio_performance(portfolio.id, user_id=user_id, db=db_session).points == []

    bench = make_series(4, n_days=60)
    fake_market.series = {BENCH: bench}
    days = [bench[-10].date, bench[-5].date]
    for day, value in zip(days, ["100000", "101000"]):
        db_session.add(
            PortfolioSnapshot(
                portfolio_id=portfolio.id,
                snapshot_date=datetime.combine(day, time.min, tzinfo=MARKET_TIMEZONE),
                total_value=Decimal(value),
                cash_balance=Decimal(value),
                invested_value=Decimal("0"),
            )
        )
    db_session.commit()

    points = read_portfolio_performance(portfolio.id, user_id=user_id, db=db_session).points

    assert [p.date for p in points] == days
    assert points[0].benchmark == Decimal("100000.00")
    expected = (Decimal("100000") * bench[-5].close / bench[-10].close).quantize(Decimal("0.01"))
    assert points[1].benchmark == expected
    assert points[1].portfolio == Decimal("101000.00")
