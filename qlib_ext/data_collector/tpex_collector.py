"""Reads cached TPEx daily price data and writes Qlib CSV staging files."""
from __future__ import annotations

import logging
from pathlib import Path

from qlib_ext.data_collector.twse_collector import TWSECollector

logger = logging.getLogger(__name__)


class TPExCollector(TWSECollector):
    """Reads cached TPEx (OTC) daily price data → writes Qlib CSV staging files."""

    MARKET_TYPE = "TPEx"
