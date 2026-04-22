"""Qlib extensions for Taiwan market — init helper and collector registry."""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER_URI = Path("workspace/qlib_data")


def init_tw_qlib(provider_uri: str | Path | None = None) -> None:
    """Initialize Qlib with Taiwan region settings."""
    import qlib
    from qlib.constant import REG_TW

    os.environ.setdefault("MLFLOW_TRACKING_URI", "file:workspace/mlruns")
    uri = str(provider_uri or DEFAULT_PROVIDER_URI)
    qlib.init(provider_uri=uri, region=REG_TW)
    logger.info("Qlib initialized with provider_uri=%s region=REG_TW", uri)
