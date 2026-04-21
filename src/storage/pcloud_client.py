"""pCloud API client - Phase 0 mock skeleton"""
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PCloudClient:
    """pCloud API wrapper. 無 token 時自動進 mock mode."""

    def __init__(self, token: Optional[str] = None, region: str = "eu"):
        self.token = token or os.getenv("PCLOUD_TOKEN")
        self.region = region or os.getenv("PCLOUD_REGION", "eu")
        self.mock_mode = not self.token
        self.base_url = (
            "https://eapi.pcloud.com" if self.region == "eu"
            else "https://api.pcloud.com"
        )
        if self.mock_mode:
            logger.warning("PCloudClient: running in MOCK mode (no token)")

    def mkdir(self, remote_path: str) -> dict:
        if self.mock_mode:
            logger.info(f"[MOCK] mkdir {remote_path}")
            return {"mock": True, "path": remote_path}
        raise NotImplementedError("Real API impl in Phase 2")

    def upload_file(self, local_path: Path, remote_path: str) -> dict:
        if self.mock_mode:
            logger.info(f"[MOCK] upload {local_path} -> {remote_path}")
            return {"mock": True, "local": str(local_path), "remote": remote_path}
        raise NotImplementedError("Real API impl in Phase 2")

    def download_file(self, remote_path: str, local_path: Path) -> dict:
        if self.mock_mode:
            logger.info(f"[MOCK] download {remote_path} -> {local_path}")
            return {"mock": True, "remote": remote_path, "local": str(local_path)}
        raise NotImplementedError("Real API impl in Phase 2")

    def list_folder(self, remote_path: str) -> list:
        if self.mock_mode:
            logger.info(f"[MOCK] list {remote_path}")
            return []
        raise NotImplementedError("Real API impl in Phase 2")

    def file_checksum(self, remote_path: str) -> Optional[str]:
        if self.mock_mode:
            return None
        raise NotImplementedError("Real API impl in Phase 2")
