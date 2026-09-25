import json
import re
from datetime import date

from app.services import universe as universe_module
from app.services.universe import Universe, get_universe, list_universes

NSE_SYMBOL = re.compile(r"^[A-Z0-9&-]{1,20}$")


def test_nifty50_file_is_configured_and_valid():
    universe = get_universe("NIFTY50")
    assert universe.name == "NIFTY50"
    assert universe.as_of == date(2026, 9, 25)
    assert len(universe.tickers) == 50
    assert len(set(universe.tickers)) == 50
    for ticker in universe.tickers:
        assert NSE_SYMBOL.match(ticker), ticker
        assert not ticker.endswith(".NS")


def test_nifty50_is_listed_as_configured():
    [listing] = list_universes()
    assert listing.name == "NIFTY50"
    assert listing.configured is True
    assert listing.as_of == date(2026, 9, 25)
    assert len(listing.tickers) == 50


def test_revision_is_deterministic_and_well_formed():
    first, second = get_universe("NIFTY50"), get_universe("nifty50")
    assert first.revision == second.revision
    assert re.fullmatch(r"NIFTY50@2026-09-25:[0-9a-f]{12}", first.revision)


def test_revision_changes_with_tickers_or_as_of():
    base = Universe("NIFTY50", date(2026, 9, 25), ["AAA", "BBB"])
    assert base.revision == Universe("NIFTY50", date(2026, 9, 25), ["AAA", "BBB"]).revision
    assert base.revision != Universe("NIFTY50", date(2026, 9, 25), ["AAA", "CCC"]).revision
    assert base.revision != Universe("NIFTY50", date(2026, 3, 31), ["AAA", "BBB"]).revision


def test_revision_ignores_formatting_differences_in_the_file(tmp_path, monkeypatch):
    def load(tickers):
        (tmp_path / "nifty50.json").write_text(
            json.dumps({"name": "NIFTY50", "as_of": "2026-09-25", "tickers": tickers}), encoding="utf-8"
        )
        monkeypatch.setattr(universe_module, "DATA_DIR", tmp_path)
        return get_universe("NIFTY50").revision

    assert load(["AAA", "BBB"]) == load([" aaa", "bbb.ns ", "BBB"])
