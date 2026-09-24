from datetime import date

from pydantic import BaseModel


class UniverseRead(BaseModel):
    name: str
    as_of: date | None
    tickers: list[str]
    configured: bool
