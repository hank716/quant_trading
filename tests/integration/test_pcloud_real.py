import os
import pytest


@pytest.mark.skipif(not os.getenv("PCLOUD_TOKEN"), reason="Needs token")
@pytest.mark.integration
def test_pcloud_real_upload(tmp_path):
    from src.storage.pcloud_client import PCloudClient
    c = PCloudClient()
    assert not c.mock_mode
    local = tmp_path / "test.txt"
    local.write_text("hello")
    result = c.upload_file(local, "/fin-quant-test/test.txt")
    assert "fileid" in result or "metadata" in result
