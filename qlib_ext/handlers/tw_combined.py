"""TW Combined DataHandler — merges technical + fundamental features + label.

This is the primary handler used by training and prediction pipelines.
Replaces legacy src/features/ + src/signals/labeler.py when Qlib data is ready.
"""
from __future__ import annotations

from qlib.data.dataset.handler import DataHandlerLP

from .tw_alpha import TWAlphaHandler
from .tw_fundamental import TWFundamentalHandler


_DEFAULT_LEARN_PROCESSORS = [
    {"class": "DropnaLabel"},
    {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
]

_DEFAULT_INFER_PROCESSORS = [
    {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
    {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
]


class TWCombinedHandler(DataHandlerLP):
    """Combined technical + fundamental DataHandler for Taiwan stocks.

    Merges all feature columns from TWAlphaHandler and TWFundamentalHandler
    with the shared 20-day forward-return label.
    Falls back gracefully when fundamental fields ($rev/$roe/$gm) are absent
    by excluding those feature expressions.
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
        include_fundamental: bool = True,
        **kwargs,
    ):
        tech_fields, tech_names = TWAlphaHandler.get_feature_config()
        if include_fundamental:
            fund_fields, fund_names = TWFundamentalHandler.get_feature_config()
        else:
            fund_fields, fund_names = [], []

        all_fields = tech_fields + fund_fields
        all_names = tech_names + fund_names

        label_fields, label_names = self.get_label_config()

        data_loader = {
            "class": "QlibDataLoader",
            "kwargs": {
                "config": {
                    "feature": (all_fields, all_names),
                    "label": kwargs.pop("label", (label_fields, label_names)),
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
    def get_label_config():
        """20-day forward return label (regression) and binary threshold variant."""
        return (
            ["Ref($close, -20)/$close - 1"],
            ["LABEL_RET20D"],
        )

    @staticmethod
    def get_binary_label_config():
        """Binary label: 1 if 20-day return > 0, else 0."""
        return (
            ["Gt(Ref($close, -20)/$close - 1, 0)"],
            ["LABEL_BIN20D"],
        )
