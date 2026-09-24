"""Candidate stock universes for capital-allocation recommendations.

Named universes are loaded from JSON files in app/data/. Tickers are bare
NSE symbols (market_data appends the ".NS" suffix itself).
"""

import json
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
