"""Candidate stock universes for capital-allocation recommendations.

Named universes are loaded from JSON files in app/data/. Tickers are bare
NSE symbols (market_data appends the ".NS" suffix itself).
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import NamedTuple

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
UNIVERSE_FILES = {"NIFTY50": "nifty50.json"}
CUSTOM_UNIVERSE = "custom"
MAX_CUSTOM_TICKERS = 100


class UniverseError(Exception):
    pass


class Universe(NamedTuple):
    name: str
    as_of: date | None
    tickers: list[str]

    @property
    def revision(self) -> str:
        """Deterministic id of this exact constituent list, for reproducible
        research: "<name>@<as_of>:<first 12 hex of sha256(name, as_of, tickers)>"."""
        as_of = self.as_of.isoformat() if self.as_of else None
        digest = hashlib.sha256(json.dumps([self.name, as_of, self.tickers]).encode("utf-8"))
        return f"{self.name}@{as_of}:{digest.hexdigest()[:12]}"


@dataclass
class ExcludedTicker:
    ticker: str
    reason: str


class UniverseListing(NamedTuple):
    name: str
    as_of: date | None
    tickers: list[str]
    configured: bool


def normalize_tickers(tickers: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        symbol = raw.strip().upper().removesuffix(".NS")
        if symbol and symbol not in seen:
            seen.add(symbol)
            normalized.append(symbol)

    if not normalized:
        raise UniverseError("At least one ticker is required.")
    if len(normalized) > MAX_CUSTOM_TICKERS:
        raise UniverseError(
            f"Too many tickers ({len(normalized)}); at most {MAX_CUSTOM_TICKERS} are allowed."
        )
    return normalized


def get_universe(name: str) -> Universe:
    key = name.strip().upper()
    filename = UNIVERSE_FILES.get(key)
    if filename is None:
        available = ", ".join(sorted(UNIVERSE_FILES))
        raise UniverseError(f"Unknown universe '{name}'. Available: {available}.")

    data = json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))
    if not data.get("tickers") or not data.get("as_of"):
        raise UniverseError(
            f"Universe '{key}' is not configured yet (constituent list or as_of date missing)."
        )

    return Universe(
        name=data["name"],
        as_of=date.fromisoformat(data["as_of"]),
        tickers=normalize_tickers(data["tickers"]),
    )


def list_universes() -> list[UniverseListing]:
    """Every known universe; ones not configured yet are listed with
    configured=False, no as_of and no tickers."""
    listings = []
    for key in sorted(UNIVERSE_FILES):
        try:
            universe = get_universe(key)
        except UniverseError:
            listings.append(UniverseListing(name=key, as_of=None, tickers=[], configured=False))
        else:
            listings.append(UniverseListing(*universe, configured=True))
    return listings
