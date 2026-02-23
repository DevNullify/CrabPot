"""Tests for runtime.py."""

from unittest.mock import MagicMock

import pytest

from crabpot.runtime import DockerRuntime, WSL2Runtime


class TestDockerRuntime:
    def test_delegates_start(self):
        dm = MagicMock()
        runtime = DockerRuntime(dm)
        runtime.start()
        dm.start.assert_called_once()

    def test_delegates_stop(self):
        dm = MagicMock()
        runtime = DockerRuntime(dm)
        runtime.stop()
        dm.stop.assert_called_once()

    def test_delegates_pause(self):
        dm = MagicMock()
        runtime = DockerRuntime(dm)
        runtime.pause()
        dm.pause.assert_called_once()

    def test_delegates_resume(self):
        dm = MagicMock()
        runtime = DockerRuntime(dm)
        runtime.resume()
        dm.resume.assert_called_once()

    def test_delegates_destroy(self):
        dm = MagicMock()
        runtime = DockerRuntime(dm)
        runtime.destroy()
        dm.destroy.assert_called_once()

    def test_delegates_get_status(self):
        dm = MagicMock()
        dm.get_status.return_value = "running"
        runtime = DockerRuntime(dm)
        assert runtime.get_status() == "running"

    def test_delegates_stats_snapshot(self):
        dm = MagicMock()
        dm.stats_snapshot.return_value = {"cpu_percent": 10.0}
        runtime = DockerRuntime(dm)
        assert runtime.stats_snapshot() == {"cpu_percent": 10.0}

    def test_delegates_get_top(self):
        dm = MagicMock()
        dm.get_top.return_value = [{"CMD": "node"}]
        runtime = DockerRuntime(dm)
        assert runtime.get_top() == [{"CMD": "node"}]

    def test_delegates_exec_run(self):
        dm = MagicMock()
        dm.exec_run.return_value = "output"
        runtime = DockerRuntime(dm)
        assert runtime.exec_run("ls") == "output"

    def test_delegates_get_logs(self):
        dm = MagicMock()
        dm.get_logs.return_value = iter(["line1", "line2"])
        runtime = DockerRuntime(dm)
        assert list(runtime.get_logs(tail=10)) == ["line1", "line2"]

    def test_delegates_get_health(self):
        dm = MagicMock()
        dm.get_health.return_value = "healthy"
        runtime = DockerRuntime(dm)
        assert runtime.get_health() == "healthy"

    def test_delegates_get_start_time(self):
        dm = MagicMock()
        dm.get_start_time.return_value = "2026-01-01T00:00:00Z"
        runtime = DockerRuntime(dm)
        assert runtime.get_start_time() == "2026-01-01T00:00:00Z"

    def test_delegates_is_running(self):
        dm = MagicMock()
        dm.is_running.return_value = True
        runtime = DockerRuntime(dm)
        assert runtime.is_running() is True

    def test_setup_calls_build(self):
        dm = MagicMock()
        runtime = DockerRuntime(dm)
        runtime.setup()
        dm.build.assert_called_once()


class TestWSL2Runtime:
    def test_no_manager_raises(self):
        runtime = WSL2Runtime()
        with pytest.raises(NotImplementedError):
            runtime.start()

    def test_with_manager_delegates_start(self):
        wm = MagicMock()
        runtime = WSL2Runtime(wsl2_manager=wm)
        runtime.start()
        wm.start.assert_called_once()

    def test_with_manager_delegates_stop(self):
        wm = MagicMock()
        runtime = WSL2Runtime(wsl2_manager=wm)
        runtime.stop()
        wm.stop.assert_called_once()

    def test_pause_terminates_wsl2(self):
        wm = MagicMock()
        runtime = WSL2Runtime(wsl2_manager=wm)
        runtime.pause()
        wm.stop.assert_called_once()

    def test_events_stream_returns_empty(self):
        wm = MagicMock()
        runtime = WSL2Runtime(wsl2_manager=wm)
        assert list(runtime.events_stream()) == []

    def test_health_when_running(self):
        wm = MagicMock()
        wm.get_status.return_value = "running"
        runtime = WSL2Runtime(wsl2_manager=wm)
        assert runtime.get_health() == "healthy"

    def test_health_when_stopped(self):
        wm = MagicMock()
        wm.get_status.return_value = "stopped"
        runtime = WSL2Runtime(wsl2_manager=wm)
        assert runtime.get_health() == "unhealthy"

    def test_start_time_returns_none(self):
        wm = MagicMock()
        runtime = WSL2Runtime(wsl2_manager=wm)
        assert runtime.get_start_time() is None
