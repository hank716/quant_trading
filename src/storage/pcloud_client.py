"""pCloud API client with mock fallback."""
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

    def _get(self, endpoint: str, params: dict) -> dict:
        import urllib.request, urllib.parse, json as _json
        params["auth_token"] = self.token
        url = f"{self.base_url}/{endpoint}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = _json.loads(resp.read())
        if data.get("result", 0) != 0:
            raise RuntimeError(f"pCloud API error {data.get('result')}: {data.get('error')}")
        return data

    def mkdir(self, remote_path: str) -> dict:
        if self.mock_mode:
            logger.info(f"[MOCK] mkdir {remote_path}")
            return {"mock": True, "path": remote_path}
        parts = remote_path.rstrip("/").rsplit("/", 1)
        folder_name = parts[-1]
        try:
            parent = self._get("listfolder", {"path": parts[0] if len(parts) > 1 else "/"})
            parent_id = parent["metadata"]["folderid"]
        except Exception:
            parent_id = 0
        return self._get("createfolder", {"name": folder_name, "folderid": parent_id})

    def upload_file(self, local_path: Path, remote_path: str) -> dict:
        if self.mock_mode:
            logger.info(f"[MOCK] upload {local_path} -> {remote_path}")
            return {"mock": True, "local": str(local_path), "remote": remote_path}
        import urllib.request, urllib.parse, json as _json
        folder, filename = remote_path.rstrip("/").rsplit("/", 1)
        folder_info = self._get("listfolder", {"path": folder})
        folder_id = folder_info["metadata"]["folderid"]

        boundary = "----PCloudBoundary"
        data = local_path.read_bytes()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="filename"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + data + f"\r\n--{boundary}--\r\n".encode()

        url = f"{self.base_url}/uploadfile?folderid={folder_id}&auth_token={urllib.parse.quote(self.token)}"
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = _json.loads(resp.read())
        if result.get("result", 0) != 0:
            raise RuntimeError(f"pCloud upload error: {result.get('error')}")
        return result

    def download_file(self, remote_path: str, local_path: Path) -> dict:
        if self.mock_mode:
            logger.info(f"[MOCK] download {remote_path} -> {local_path}")
            return {"mock": True, "remote": remote_path, "local": str(local_path)}
        import urllib.request
        link_info = self._get("getfilelink", {"path": remote_path})
        hosts = link_info["hosts"]
        path = link_info["path"]
        url = f"https://{hosts[0]}{path}"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, local_path)
        return {"remote": remote_path, "local": str(local_path)}

    def list_folder(self, remote_path: str) -> list:
        if self.mock_mode:
            logger.info(f"[MOCK] list {remote_path}")
            return []
        data = self._get("listfolder", {"path": remote_path})
        return data.get("metadata", {}).get("contents", [])

    def file_checksum(self, remote_path: str) -> Optional[str]:
        if self.mock_mode:
            return None
        data = self._get("checksumfile", {"path": remote_path})
        return data.get("sha256") or data.get("md5")
