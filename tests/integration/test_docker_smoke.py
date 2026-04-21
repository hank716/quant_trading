import subprocess
import pytest


@pytest.mark.integration
def test_docker_compose_config_valid():
    result = subprocess.run(
        ["docker", "compose", "-f", "compose/docker-compose.yml", "config"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
