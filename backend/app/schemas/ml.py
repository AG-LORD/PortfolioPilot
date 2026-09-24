from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class ModelEvaluationRead(BaseModel):
    model: str
    mae: Decimal
    hit_rate: Decimal
    mean_ic: Decimal
    test_blocks: int
    as_of: date
