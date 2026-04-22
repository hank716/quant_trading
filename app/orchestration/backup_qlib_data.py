"""CLI: python -m app.orchestration.backup_qlib_data"""
from __future__ import annotations

import logging
import os
import tempfile
import zipfile
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


def _zip_to_file(directory: Path, dest: Path) -> None:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(directory))


def main() -> None:
    """Zip workspace/qlib_data/ and upload to pCloud at /qlib_data/snapshot={YYYY-MM-DD}/."""
    from src.storage.pcloud_client import PCloudClient

    qlib_data_dir = Path(os.getenv("OUTPUT_DIR", "workspace")) / "qlib_data"
    if not qlib_data_dir.exists():
        logger.warning("qlib_data dir not found at %s — skipping backup", qlib_data_dir)
        return

    client = PCloudClient(token=os.getenv("PCLOUD_TOKEN"), region=os.getenv("PCLOUD_REGION", "eu"))
    snapshot_date = date.today().isoformat()
    remote_path = f"/qlib_data/snapshot={snapshot_date}/qlib_data.zip"

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "qlib_data.zip"
        logger.info("Zipping %s ...", qlib_data_dir)
        _zip_to_file(qlib_data_dir, zip_path)
        logger.info("Uploading %d bytes to pCloud at %s", zip_path.stat().st_size, remote_path)
        client.mkdir(f"/qlib_data/snapshot={snapshot_date}")
        client.upload_file(zip_path, remote_path)

    logger.info("Backup complete: %s", remote_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
