from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from price_fakes import make_series

from app.models import DailyPrice, PriceCacheCoverage
from app.services import price_history
from app.services.market_data import MarketDataUnavailableError, PricePoint
from app.services.price_history import (
    CLOSE_SETTLE_BUFFER,
    FULL_REFRESH_MAX_AGE,
    MARKET_CLOSE,
    SEAM_TOLERANCE,
    get_price_history,
)
from app.services.snapshots import MARKET_TIMEZONE

A, B, C = "ZZTEST_A", "ZZTEST_B", "ZZTEST_C"
SERIES_END = date(2026, 4, 30)
JAN1, FEB1, MAR1 = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)


def _weekday_series(seed=1):
    # Weekend gaps stand in for holidays: dates inside coverage with no rows.
    return make_series(seed, n_days=180, end=SERIES_END, weekdays_only=True)


def _in_range(series, start, end):
    return [p for p in series if start <= p.date < end]


def _row_count(db, ticker):
    return db.query(DailyPrice).filter(DailyPrice.ticker == ticker).count()


def _set_clock(monkeypatch, moment: datetime):
    monkeypatch.setattr(price_history, "_now", lambda: moment)


def test_cache_miss_fetches_and_stores_then_second_call_makes_no_download(db_session, fake_market):
    series = _weekday_series()
    fake_market.series = {A: series}

    first = get_price_history(db_session, [A], JAN1, MAR1)
    assert len(fake_market.calls) == 1
    assert first.points[A] == _in_range(series, JAN1, MAR1)
    assert _row_count(db_session, A) == len(_in_range(series, JAN1, MAR1))

    second = get_price_history(db_session, [A], JAN1, MAR1)
    assert len(fake_market.calls) == 1
    assert second.points[A] == first.points[A]


def test_partial_coverage_fetches_only_missing_right_edge(db_session, fake_market):
    series = _weekday_series()
    fake_market.series = {A: series}
    get_price_history(db_session, [A], JAN1, FEB1)
    last_cached = _in_range(series, JAN1, FEB1)[-1].date

    result = get_price_history(db_session, [A], JAN1, MAR1)

    assert len(fake_market.calls) == 2
    _, start, end = fake_market.calls[1]
    assert (start, end) == (last_cached, MAR1)  # seam day + missing edge only
    assert result.points[A] == _in_range(series, JAN1, MAR1)
    assert _row_count(db_session, A) == len(_in_range(series, JAN1, MAR1))


def test_partial_coverage_fetches_only_missing_left_edge(db_session, fake_market):
    series = _weekday_series()
    fake_market.series = {A: series}
    get_price_history(db_session, [A], FEB1, MAR1)
    first_cached = _in_range(series, FEB1, MAR1)[0].date

    result = get_price_history(db_session, [A], JAN1, MAR1)

    _, start, end = fake_market.calls[1]
    assert (start, end) == (JAN1, first_cached + timedelta(days=1))
    assert result.points[A] == _in_range(series, JAN1, MAR1)


def test_request_inside_coverage_makes_no_download_even_with_empty_dates(db_session, fake_market):
    fake_market.series = {A: _weekday_series()}
    get_price_history(db_session, [A], JAN1, MAR1)

    weekend = get_price_history(db_session, [A], date(2026, 1, 3), date(2026, 1, 5))  # Sat-Sun
    inner = get_price_history(db_session, [A], date(2026, 1, 10), date(2026, 2, 10))

    assert len(fake_market.calls) == 1
    assert weekend.errors[A].reason == "no historical data returned"
    assert len(inner.points[A]) > 0


def test_pre_listing_range_is_not_requested_again(db_session, fake_market):
    series = make_series(1, n_days=40, end=date(2026, 2, 20))  # "lists" mid-January
    fake_market.series = {A: series}
    get_price_history(db_session, [A], JAN1, MAR1)
    get_price_history(db_session, [A], JAN1, MAR1)

    assert len(fake_market.calls) == 1
    coverage = db_session.get(PriceCacheCoverage, A)
    assert coverage.covered_start == JAN1


def test_missing_tickers_fetched_in_single_batched_call(db_session, fake_market):
    fake_market.series = {A: _weekday_series(1), B: _weekday_series(2), C: _weekday_series(3)}

    result = get_price_history(db_session, [A, B, C], JAN1, MAR1)

    assert len(fake_market.calls) == 1
    assert sorted(fake_market.calls[0][0]) == [A, B, C]
    assert all(len(result.points[t]) > 0 for t in (A, B, C))


def test_upsert_never_duplicates_rows(db_session, fake_market):
    series = _weekday_series()
    fake_market.series = {A: series}
    expected = len(_in_range(series, JAN1, MAR1))

    get_price_history(db_session, [A], JAN1, MAR1)
    get_price_history(db_session, [A], JAN1, MAR1, force_refresh=True)
    price_history._upsert_prices(
        db_session, A, _in_range(series, JAN1, MAR1), datetime.now(MARKET_TIMEZONE)
    )
    db_session.commit()

    assert _row_count(db_session, A) == expected


def test_today_not_stored_before_close_buffer_and_stored_after(db_session, fake_market, monkeypatch):
    today = date(2026, 3, 10)  # a Tuesday
    fake_market.series = {A: make_series(1, n_days=30, end=today)}
    close_ready = datetime.combine(today, MARKET_CLOSE, tzinfo=MARKET_TIMEZONE) + CLOSE_SETTLE_BUFFER
    tomorrow = today + timedelta(days=1)

    _set_clock(monkeypatch, close_ready - timedelta(minutes=1))
    before = get_price_history(db_session, [A], today - timedelta(days=10), tomorrow)
    assert before.points[A][-1].date == today - timedelta(days=1)
    assert db_session.get(PriceCacheCoverage, A).covered_end == today - timedelta(days=1)

    _set_clock(monkeypatch, close_ready)
    after = get_price_history(db_session, [A], today - timedelta(days=10), tomorrow)
    assert after.points[A][-1].date == today
    db_session.expire_all()
    assert db_session.get(PriceCacheCoverage, A).covered_end == today


def test_stale_coverage_triggers_full_refresh(db_session, fake_market):
    fake_market.series = {A: _weekday_series()}
    get_price_history(db_session, [A], JAN1, MAR1)

    coverage = db_session.get(PriceCacheCoverage, A)
    coverage.last_full_refresh_at = datetime.now(MARKET_TIMEZONE) - FULL_REFRESH_MAX_AGE - timedelta(hours=1)
    db_session.commit()

    get_price_history(db_session, [A], date(2026, 1, 10), date(2026, 1, 20))

    assert len(fake_market.calls) == 2
    _, start, end = fake_market.calls[1]
    assert (start, end) == (JAN1, MAR1)  # whole covered window, not just the request
    db_session.expire_all()
    refreshed = db_session.get(PriceCacheCoverage, A).last_full_refresh_at
    assert datetime.now(MARKET_TIMEZONE) - refreshed < timedelta(minutes=5)


def test_force_refresh_triggers_full_refresh(db_session, fake_market):
    fake_market.series = {A: _weekday_series()}
    get_price_history(db_session, [A], JAN1, MAR1)

    get_price_history(db_session, [A], JAN1, MAR1, force_refresh=True)

    assert len(fake_market.calls) == 2
    assert fake_market.calls[1][1:] == (JAN1, MAR1)


def _rebased(series, factor):
    return [
        PricePoint(p.date, p.open * factor, p.high * factor, p.low * factor, p.close * factor, p.volume)
        for p in series
    ]


def test_seam_mismatch_triggers_full_refresh_and_replaces_rows(db_session, fake_market):
    series = _weekday_series()
    fake_market.series = {A: series}
    get_price_history(db_session, [A], JAN1, FEB1)

    # A dividend re-bases all history by more than the tolerance.
    rebased = _rebased(series, Decimal("0.98"))
    fake_market.series = {A: rebased}
    result = get_price_history(db_session, [A], JAN1, MAR1)

    assert len(fake_market.calls) == 3  # initial, incremental with seam, full refresh
    assert fake_market.calls[2][1:] == (JAN1, MAR1)
    assert result.points[A] == _in_range(rebased, JAN1, MAR1)
    assert _row_count(db_session, A) == len(_in_range(rebased, JAN1, MAR1))


def test_seam_within_tolerance_stays_incremental(db_session, fake_market):
    series = _weekday_series()
    fake_market.series = {A: series}
    get_price_history(db_session, [A], JAN1, FEB1)

    fake_market.series = {A: _rebased(series, 1 + SEAM_TOLERANCE / 2)}
    result = get_price_history(db_session, [A], JAN1, MAR1)

    assert len(fake_market.calls) == 2
    # January rows (including the seam day) keep their original cached values.
    assert result.points[A][: len(_in_range(series, JAN1, FEB1))] == _in_range(series, JAN1, FEB1)


def test_batch_failure_reports_request_failed_reason(db_session, fake_market):
    fake_market.fail = MarketDataUnavailableError(f"{A}, {B}", "history request failed: boom")

    result = get_price_history(db_session, [A, B], JAN1, MAR1)

    assert result.errors[A].reason == "history request failed: boom"
    assert result.errors[B].reason == "history request failed: boom"
    assert db_session.get(PriceCacheCoverage, A) is None


@pytest.mark.parametrize(
    "moment, expected",
    [
        (datetime(2026, 3, 10, 15, 59, tzinfo=MARKET_TIMEZONE), date(2026, 3, 9)),
        (datetime(2026, 3, 10, 16, 0, tzinfo=MARKET_TIMEZONE), date(2026, 3, 10)),
        (datetime(2026, 3, 10, 2, 0, tzinfo=MARKET_TIMEZONE), date(2026, 3, 9)),
    ],
)
def test_last_completed_trading_day(moment, expected):
    assert price_history.last_completed_trading_day(moment) == expected
