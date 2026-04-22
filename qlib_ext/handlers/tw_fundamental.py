"""TW Fundamental DataHandler — financial statement features.

Requires that FinancialCollector has already binned monthly revenue and
quarterly financial data into provider_uri/features/{symbol}/.
Fields expected: $rev (monthly revenue), $roe (quarterly ROE), $gm (gross margin).
"""
from __future__ import annotations

from qlib.data.dataset.handler import DataHandlerLP


_DEFAULT_LEARN_PROCESSORS = [
    {"class": "DropnaLabel"},
    {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
]

_DEFAULT_INFER_PROCESSORS = [
    {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
    {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
]


class TWFundamentalHandler(DataHandlerLP):
    """Fundamental DataHandler for Taiwan stocks.

    Features mirror the legacy src/features/fund_features.py signals.
    Requires $rev, $roe, $gm fields to be present in the provider.
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

        # Revenue YoY: current month vs same month last year
        fields.append("$rev/Ref($rev, 252) - 1")
        names.append("FUND_REV_YOY")

        # Revenue MoM
        fields.append("$rev/Ref($rev, 21) - 1")
        names.append("FUND_REV_MOM")

        # Consecutive months of positive revenue growth (proxy: sign of MoM)
        # Use rolling sum of positive flags over 3 months
        fields.append("Mean(If(Gt($rev/Ref($rev,21)-1, 0), 1, 0), 63)")
        names.append("FUND_REV_POS_RATIO_3M")

        # ROE level
        fields.append("$roe")
        names.append("FUND_ROE")

        # ROE YoY improvement
        fields.append("$roe - Ref($roe, 252)")
        names.append("FUND_ROE_YOY")

        # Gross margin level
        fields.append("$gm")
        names.append("FUND_GM")

        # Gross margin YoY improvement
        fields.append("$gm - Ref($gm, 252)")
        names.append("FUND_GM_YOY")

        return fields, names

    @staticmethod
    def get_label_config():
        return ["Ref($close, -20)/$close - 1"], ["LABEL_RET20D"]
