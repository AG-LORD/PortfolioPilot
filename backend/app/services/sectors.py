"""Static ticker -> sector labels (app/data/sectors.json).

Display metadata only: the optimizer's sector constraint stays inactive, so
nothing here affects a recommendation. Unknown tickers return None.
"""

import json
from functools import lru_cache
from pathlib import Path

SECTORS_PATH = Path(__file__).resolve().parents[1] / "data" / "sectors.json"


@lru_cache(maxsize=1)
def load_sectors() -> dict[str, str]:
    return json.loads(SECTORS_PATH.read_text(encoding="utf-8"))


def get_sector(ticker: str) -> str | None:
    return load_sectors().get(ticker.upper())
