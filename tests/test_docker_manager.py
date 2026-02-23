"""Tests for docker_manager.py."""

from unittest.mock import MagicMock, patch

import pytest

from crabpot.docker_manager import DockerManager


@pytest.fixture
def mock_docker_client():
    """Create a mock Docker client."""
    with patch("crabpot.docker_manager.docker") as mock_docker:
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        yield mock_client


@pytest.fixture
def dm(mock_docker_client, tmp_path):
    """Create a DockerManager with mocked Docker client."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return DockerManager(config_dir=config_dir)


class TestDockerManager:
    def test_get_status_running(self, dm, mock_docker_client):
        container = MagicMock()
        container.status = "running"
        mock_docker_client.containers.get.return_value = container

        assert dm.get_status() == "running"

    def test_get_status_not_found(self, dm, mock_docker_client):
        from docker.errors import NotFound

        mock_docker_client.containers.get.side_effect = NotFound("not found")

        assert dm.get_status() == "not_found"

    def test_is_running(self, dm, mock_docker_client):
        container = MagicMock()
        container.status = "running"
        mock_docker_client.containers.get.return_value = container

        assert dm.is_running() is True

    def test_is_not_running(self, dm, mock_docker_client):
        container = MagicMock()
        container.status = "exited"
        mock_docker_client.containers.get.return_value = container

        assert dm.is_running() is False

    def test_pause_running_container(self, dm, mock_docker_client):
        container = MagicMock()
        container.status = "running"
        mock_docker_client.containers.get.return_value = container

        dm.pause()
        container.pause.assert_called_once()

    def test_pause_non_running_raises(self, dm, mock_docker_client):
        container = MagicMock()
        container.status = "exited"
        mock_docker_client.containers.get.return_value = container

        with pytest.raises(RuntimeError, match="Cannot pause"):
            dm.pause()

    def test_resume_paused_container(self, dm, mock_docker_client):
        container = MagicMock()
        container.status = "paused"
        mock_docker_client.containers.get.return_value = container

        dm.resume()
        container.unpause.assert_called_once()

    def test_resume_non_paused_raises(self, dm, mock_docker_client):
        container = MagicMock()
        container.status = "running"
        mock_docker_client.containers.get.return_value = container

        with pytest.raises(RuntimeError, match="not paused"):
            dm.resume()

    def test_stop_paused_container_unpauses_first(self, dm, mock_docker_client):
        container = MagicMock()
        container.status = "paused"
        mock_docker_client.containers.get.return_value = container

        dm.stop()
        container.unpause.assert_called_once()
        container.stop.assert_called_once_with(timeout=30)

    def test_stop_not_found(self, dm, mock_docker_client):
        from docker.errors import NotFound

        mock_docker_client.containers.get.side_effect = NotFound("not found")

        # Should not raise
        dm.stop()

    def test_get_top(self, dm, mock_docker_client):
        container = MagicMock()
        container.status = "running"
        container.top.return_value = {
            "Titles": ["PID", "CMD"],
            "Processes": [["1", "node app.js"], ["42", "npm start"]],
        }
        mock_docker_client.containers.get.return_value = container

        procs = dm.get_top()
        assert len(procs) == 2
        assert procs[0]["CMD"] == "node app.js"

    def test_parse_stats(self):
        raw = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200},
                "system_cpu_usage": 1000,
                "online_cpus": 2,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 500,
            },
            "memory_stats": {"usage": 512 * 1024 * 1024, "limit": 2 * 1024 * 1024 * 1024},
            "networks": {
                "eth0": {"rx_bytes": 1000000, "tx_bytes": 500000},
            },
            "pids_stats": {"current": 42},
            "read": "2026-01-01T00:00:00Z",
        }

        parsed = DockerManager._parse_stats(raw)

        assert parsed["cpu_percent"] == 40.0  # (100/500) * 2 * 100
        assert parsed["memory_usage"] == 512 * 1024 * 1024
        assert parsed["memory_limit"] == 2 * 1024 * 1024 * 1024
        assert parsed["network_rx"] == 1000000
        assert parsed["network_tx"] == 500000
        assert parsed["pids"] == 42

    def test_get_health(self, dm, mock_docker_client):
        container = MagicMock()
        container.attrs = {"State": {"Health": {"Status": "healthy"}}}
        mock_docker_client.containers.get.return_value = container

        assert dm.get_health() == "healthy"

    def test_get_start_time(self, dm, mock_docker_client):
        container = MagicMock()
        container.attrs = {"State": {"StartedAt": "2026-01-01T00:00:00Z"}}
        mock_docker_client.containers.get.return_value = container

        assert dm.get_start_time() == "2026-01-01T00:00:00Z"
