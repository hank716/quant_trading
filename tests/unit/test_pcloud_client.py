from src.storage.pcloud_client import PCloudClient


def test_mock_mode_when_no_token(monkeypatch):
    monkeypatch.delenv("PCLOUD_TOKEN", raising=False)
    c = PCloudClient()
    assert c.mock_mode is True

def test_mock_mkdir_returns_dict(monkeypatch):
    monkeypatch.delenv("PCLOUD_TOKEN", raising=False)
    c = PCloudClient()
    result = c.mkdir("/test")
    assert result["mock"] is True

def test_mock_upload(monkeypatch, tmp_path):
    monkeypatch.delenv("PCLOUD_TOKEN", raising=False)
    c = PCloudClient()
    local = tmp_path / "f.txt"
    local.write_text("x")
    result = c.upload_file(local, "/remote/f.txt")
    assert result["mock"] is True
