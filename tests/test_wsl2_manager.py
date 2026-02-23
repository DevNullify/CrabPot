"""Tests for wsl2_manager.py."""

from unittest.mock import MagicMock, patch

import pytest

from crabpot.wsl2_manager import WSL2Manager


@pytest.fixture
def wsl2_dir(tmp_path):
    return tmp_path / "wsl2"


@pytest.fixture
def manager(wsl2_dir):
    return WSL2Manager(distro_name="TestCrabPot", wsl2_dir=wsl2_dir)


class TestWSL2ManagerStart:
    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_start(self, mock_run, manager):
        mock_run.return_value = MagicMock(returncode=0)
        manager.start()
        mock_run.assert_called_once_with(
            ["wsl", "-d", "TestCrabPot", "--exec", "/bin/true"],
            check=True,
            capture_output=True,
            text=True,
        )


class TestWSL2ManagerStop:
    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_stop(self, mock_run, manager):
        mock_run.return_value = MagicMock(returncode=0)
        manager.stop()
        mock_run.assert_called_once_with(
            ["wsl", "-t", "TestCrabPot"],
            check=True,
            capture_output=True,
            text=True,
        )


class TestWSL2ManagerDestroy:
    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_destroy_unregisters(self, mock_run, manager, wsl2_dir):
        mock_run.return_value = MagicMock(returncode=0)
        wsl2_dir.mkdir(parents=True)
        manager.destroy()
        mock_run.assert_called_once_with(
            ["wsl", "--unregister", "TestCrabPot"],
            check=False,
            capture_output=True,
            text=True,
        )

    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_destroy_cleans_dir(self, mock_run, manager, wsl2_dir):
        mock_run.return_value = MagicMock(returncode=0)
        wsl2_dir.mkdir(parents=True)
        (wsl2_dir / "test.txt").write_text("data")
        manager.destroy()
        assert not wsl2_dir.exists()


class TestWSL2ManagerStatus:
    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_status_running(self, mock_run, manager):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  NAME           STATE           VERSION\n* TestCrabPot    Running         2\n",
        )
        assert manager.get_status() == "running"

    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_status_stopped(self, mock_run, manager):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  NAME           STATE           VERSION\n  TestCrabPot    Stopped         2\n",
        )
        assert manager.get_status() == "stopped"

    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_status_not_found(self, mock_run, manager):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  NAME           STATE           VERSION\n  Ubuntu         Running         2\n",
        )
        assert manager.get_status() == "not_found"

    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_status_wsl_not_installed(self, mock_run, manager):
        mock_run.side_effect = FileNotFoundError("wsl not found")
        assert manager.get_status() == "not_found"

    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_status_timeout(self, mock_run, manager):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("wsl", 10)
        assert manager.get_status() == "not_found"


class TestWSL2ManagerExec:
    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_exec_run(self, mock_run, manager):
        mock_run.return_value = MagicMock(returncode=0, stdout="hello world\n")
        result = manager.exec_run("echo hello world")
        assert result == "hello world\n"
        mock_run.assert_called_once_with(
            ["wsl", "-d", "TestCrabPot", "--exec", "sh", "-c", "echo hello world"],
            capture_output=True,
            text=True,
            timeout=30,
        )


class TestWSL2ManagerLogs:
    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_get_logs(self, mock_run, manager):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="line1\nline2\nline3\n",
        )
        logs = list(manager.get_logs(tail=50))
        assert logs == ["line1", "line2", "line3"]


class TestWSL2ManagerStats:
    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_get_stats(self, mock_run, manager):
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "meminfo" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout="MemTotal:        8000000 kB\nMemAvailable:    4000000 kB\n",
                )
            elif "loadavg" in cmd_str:
                return MagicMock(returncode=0, stdout="0.50 0.40 0.30 1/200 12345\n")
            elif "grep" in cmd_str:
                return MagicMock(returncode=0, stdout="42\n")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = side_effect
        stats = manager.get_stats()

        assert stats is not None
        assert stats["memory_usage"] == 4000000 * 1024  # 4GB used
        assert stats["memory_limit"] == 8000000 * 1024
        assert stats["memory_percent"] == 50.0
        assert stats["cpu_percent"] == 50.0  # 0.5 * 100
        assert stats["pids"] == 42

    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_get_stats_failure_returns_none(self, mock_run, manager):
        mock_run.side_effect = Exception("connection failed")
        assert manager.get_stats() is None


class TestWSL2ManagerImport:
    @patch("crabpot.wsl2_manager.subprocess.run")
    def test_import_distro(self, mock_run, manager, wsl2_dir):
        mock_run.return_value = MagicMock(returncode=0)
        rootfs = wsl2_dir / "rootfs.tar"
        wsl2_dir.mkdir(parents=True)
        rootfs.write_text("fake")

        manager._import_distro(rootfs)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "--import" in call_args
        assert "TestCrabPot" in call_args
        assert "--version" in call_args
        assert "2" in call_args
