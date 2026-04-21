from datetime import date
from typing import Literal
from pydantic import BaseModel, Field


class PositionRecord(BaseModel):
    trade_date: date
    instrument: str
    target_weight: float = Field(ge=0, le=1)
    notional: float
    score: float
    selection_reason: str


class TradeRecord(BaseModel):
    trade_date: date
    instrument: str
    action: Literal["BUY", "SELL", "HOLD"]
    delta_weight: float
    prev_weight: float
    new_weight: float
    reason: str
