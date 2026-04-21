from datetime import date
from pydantic import BaseModel


class SignalRecord(BaseModel):
    trade_date: date
    instrument: str
    score: float
    bar_freq: str = "1d"
    model_id: str
    feature_set_version: str = "v1"
    data_snapshot_id: str
