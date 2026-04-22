"""TW Alpha DataHandler — technical features from OHLCV price/volume data."""
from __future__ import annotations

from typing import List

from qlib.data.dataset.handler import DataHandlerLP
from qlib.data.dataset.processor import RobustZScoreNorm, Fillna


_DEFAULT_LEARN_PROCESSORS = [
    {"class": "DropnaLabel"},
    {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
]

_DEFAULT_INFER_PROCESSORS = [
    {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
    {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
]


class TWAlphaHandler(DataHandlerLP):
    """Technical-only DataHandler for Taiwan stocks.

    Features mirror the legacy src/features/tech_features.py signals:
    - MA-return at 5/10/20/60 windows (TECH_MAn_RET)
    - Volume ratio at 5/10/20 windows  (TECH_VOLn_RATIO)
    - Institutional flow features if binned (optional)
    """

    def __init__(
        self,
        instruments="all",
        start_time=None,
        end_time=None,
        freq="day",
        infer_processors=_DEFAULT_INFER_PROCESSORS,
        learn_processors=_DEFAULT_LEARN_PROCESSORS,
        fit_start_time=None,
        fit_end_time=None,
        process_type=DataHandlerLP.PTYPE_A,
        filter_pipe=None,
        inst_processors=None,
        **kwargs,
    ):
        data_loader = {
            "class": "QlibDataLoader",
            "kwargs": {
                "config": {
                    "feature": self.get_feature_config(),
                    "label": kwargs.pop("label", self.get_label_config()),
                },
                "filter_pipe": filter_pipe,
                "freq": freq,
                "inst_processors": inst_processors,
            },
        }
        super().__init__(
            instruments=instruments,
            start_time=start_time,
            end_time=end_time,
            data_loader=data_loader,
            infer_processors=infer_processors,
            learn_processors=learn_processors,
            process_type=process_type,
            **kwargs,
        )

    @staticmethod
    def get_feature_config():
        fields: list[str] = []
        names: list[str] = []

        # MA-return: (MA_n / close) - 1, captures mean-reversion / momentum
        for n in [5, 10, 20, 60]:
            fields.append(f"Mean($close, {n})/$close - 1")
            names.append(f"TECH_MA{n}_RET")

        # Volume ratio: today's volume vs rolling average
        for n in [5, 10, 20]:
            fields.append(f"$volume/(Mean($volume, {n})+1e-12)")
            names.append(f"TECH_VOL{n}_RATIO")

        # Price momentum: n-day return
        for n in [5, 10, 20]:
            fields.append(f"$close/Ref($close, {n}) - 1")
            names.append(f"TECH_RET{n}D")

        # Volatility: std of log returns
        for n in [10, 20]:
            fields.append(f"Std($close/Ref($close,1)-1, {n})")
            names.append(f"TECH_STD{n}D")

        # High-low range ratio
        fields.append("($high-$low)/($close+1e-12)")
        names.append("TECH_HL_RANGE")

        return fields, names

    @staticmethod
    def get_label_config():
        return ["Ref($close, -20)/$close - 1"], ["LABEL_RET20D"]
