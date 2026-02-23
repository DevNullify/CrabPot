"""Tests for cli.py command handlers."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from crabpot.cli import _create_runtime, dispatch


class TestDispatch:
    def test_unknown_command_exits(self, capsys):
        args = argparse.Namespace(command="nonexistent")
        with pytest.raises(SystemExit):
            dispatch(args)

    def test_none_command_does_not_crash(self):
        args = argparse.Namespace(command=None)
        with pytest.raises(SystemExit):
            dispatch(args)


class TestCreateRuntime:
    @patch("crabpot.docker_manager.DockerManager")
    @patch("crabpot.runtime.DockerRuntime")
    def test_docker_target(self, mock_runtime_cls, mock_dm_cls):
        """Docker target creates DockerRuntime wrapping DockerManager."""
        config = MagicMock()
        config.target = "docker"
        runtime = _create_runtime(config)
        mock_dm_cls.assert_called_once()
        mock_runtime_cls.assert_called_once()
        assert runtime == mock_runtime_cls.return_value

    @patch("crabpot.wsl2_manager.WSL2Manager")
    @patch("crabpot.runtime.WSL2Runtime")
    def test_wsl2_target(self, mock_runtime_cls, mock_wm_cls):
        """WSL2 target creates WSL2Runtime wrapping WSL2Manager."""
        config = MagicMock()
        config.target = "wsl2"
        config.wsl2.distro_name = "CrabPot"
        runtime = _create_runtime(config)
        mock_wm_cls.assert_called_once()
        mock_runtime_cls.assert_called_once()
        assert runtime == mock_runtime_cls.return_value


class TestCmdInit:
    @patch("crabpot.config.save_config")
    @patch("crabpot.docker_manager.DockerManager.check_docker")
    def test_init_non_interactive(self, mock_check, mock_save, tmp_path):
        mock_check.return_value = {
            "installed": True,
            "running": True,
            "compose": True,
            "version": "Docker version 24.0.7",
        }
        args = argparse.Namespace(
            command="init",
            target="docker",
            preset="standard",
            openclaw_tag="latest",
            non_interactive=True,
        )
        with (
            patch("crabpot.cli.CONFIG_FILE", tmp_path / "crabpot.yml"),
            patch("crabpot.cli.CONFIG_DIR", tmp_path / "config"),
            patch("crabpot.cli.DATA_DIR", tmp_path / "data"),
        ):
            dispatch(args)
        mock_save.assert_called_once()

    @patch("crabpot.docker_manager.DockerManager.check_docker")
    def test_init_no_docker(self, mock_check):
        mock_check.return_value = {
            "installed": False,
            "running": False,
            "compose": False,
            "version": "",
        }
        args = argparse.Namespace(
            command="init",
            target="docker",
            preset="standard",
            openclaw_tag="latest",
            non_interactive=True,
        )
        with pytest.raises(SystemExit):
            dispatch(args)


class TestCmdConfig:
    def test_config_show_no_file(self, tmp_path, capsys):
        args = argparse.Namespace(command="config", action="show")
        with patch("crabpot.cli.CONFIG_FILE", tmp_path / "missing.yml"):
            dispatch(args)

    def test_config_reset(self, tmp_path):
        config_file = tmp_path / "crabpot.yml"
        args = argparse.Namespace(command="config", action="reset")
        with patch("crabpot.cli.CONFIG_FILE", config_file):
            dispatch(args)
        assert config_file.exists()
        content = config_file.read_text()
        assert "standard" in content

    def test_config_show_with_file(self, tmp_path, capsys):
        config_file = tmp_path / "crabpot.yml"
        config_file.write_text("target: docker\nsecurity:\n  preset: paranoid\n")
        args = argparse.Namespace(command="config", action="show")
        with patch("crabpot.cli.CONFIG_FILE", config_file):
            dispatch(args)


class TestCmdStop:
    @patch("crabpot.cli._create_runtime")
    @patch("crabpot.config.load_config")
    def test_stop_not_found(self, mock_load, mock_create, capsys):
        mock_runtime = MagicMock()
        mock_runtime.get_status.return_value = "not_found"
        mock_create.return_value = mock_runtime
        args = argparse.Namespace(command="stop")
        dispatch(args)
        mock_runtime.stop.assert_not_called()

    @patch("crabpot.cli._create_runtime")
    @patch("crabpot.config.load_config")
    def test_stop_running(self, mock_load, mock_create):
        mock_runtime = MagicMock()
        mock_runtime.get_status.return_value = "running"
        mock_create.return_value = mock_runtime
        args = argparse.Namespace(command="stop")
        dispatch(args)
        mock_runtime.stop.assert_called_once()


class TestCmdPause:
    @patch("crabpot.cli._create_runtime")
    @patch("crabpot.config.load_config")
    def test_pause(self, mock_load, mock_create):
        mock_runtime = MagicMock()
        mock_create.return_value = mock_runtime
        args = argparse.Namespace(command="pause")
        dispatch(args)
        mock_runtime.pause.assert_called_once()


class TestCmdResume:
    @patch("crabpot.cli._create_runtime")
    @patch("crabpot.config.load_config")
    def test_resume(self, mock_load, mock_create):
        mock_runtime = MagicMock()
        mock_create.return_value = mock_runtime
        args = argparse.Namespace(command="resume")
        dispatch(args)
        mock_runtime.resume.assert_called_once()


class TestCmdStatus:
    @patch("crabpot.cli._create_runtime")
    @patch("crabpot.config.load_config")
    def test_status_not_found(self, mock_load, mock_create, tmp_path, capsys):
        mock_runtime = MagicMock()
        mock_runtime.get_status.return_value = "not_found"
        mock_runtime.get_health.return_value = None
        mock_runtime.get_start_time.return_value = None
        mock_create.return_value = mock_runtime
        args = argparse.Namespace(command="status")
        with patch("crabpot.cli.DATA_DIR", tmp_path):
            dispatch(args)

    @patch("crabpot.cli._create_runtime")
    @patch("crabpot.config.load_config")
    def test_status_running_with_stats(self, mock_load, mock_create, tmp_path):
        mock_runtime = MagicMock()
        mock_runtime.get_status.return_value = "running"
        mock_runtime.get_health.return_value = "healthy"
        mock_runtime.get_start_time.return_value = "2026-01-01T00:00:00Z"
        mock_runtime.stats_snapshot.return_value = {
            "cpu_percent": 10.0,
            "memory_usage": 100 * 1024 * 1024,
            "memory_limit": 2048 * 1024 * 1024,
            "memory_percent": 4.9,
            "pids": 15,
            "network_rx": 1024 * 1024,
            "network_tx": 512 * 1024,
        }
        mock_create.return_value = mock_runtime
        args = argparse.Namespace(command="status")
        with patch("crabpot.cli.DATA_DIR", tmp_path):
            dispatch(args)


class TestCmdLogs:
    @patch("crabpot.cli._create_runtime")
    @patch("crabpot.config.load_config")
    def test_logs_not_found(self, mock_load, mock_create):
        mock_runtime = MagicMock()
        mock_runtime.get_status.return_value = "not_found"
        mock_create.return_value = mock_runtime
        args = argparse.Namespace(command="logs", follow=False, tail=10)
        with pytest.raises(SystemExit):
            dispatch(args)

    @patch("crabpot.cli._create_runtime")
    @patch("crabpot.config.load_config")
    def test_logs_streams_output(self, mock_load, mock_create, capsys):
        mock_runtime = MagicMock()
        mock_runtime.get_status.return_value = "running"
        mock_runtime.get_logs.return_value = iter(["line1", "line2"])
        mock_create.return_value = mock_runtime
        args = argparse.Namespace(command="logs", follow=False, tail=10)
        dispatch(args)
        mock_runtime.get_logs.assert_called_once_with(follow=False, tail=10)


class TestCmdShell:
    @patch("crabpot.cli._create_runtime")
    @patch("crabpot.config.load_config")
    def test_shell_not_running(self, mock_load, mock_create):
        mock_runtime = MagicMock()
        mock_runtime.get_status.return_value = "stopped"
        mock_create.return_value = mock_runtime
        args = argparse.Namespace(command="shell")
        with pytest.raises(SystemExit):
            dispatch(args)

    @patch("crabpot.cli._create_runtime")
    @patch("crabpot.config.load_config")
    def test_shell_opens(self, mock_load, mock_create):
        mock_runtime = MagicMock()
        mock_runtime.get_status.return_value = "running"
        mock_create.return_value = mock_runtime
        args = argparse.Namespace(command="shell")
        dispatch(args)
        mock_runtime.open_shell.assert_called_once()


class TestCmdDestroy:
    @patch("builtins.input", return_value="destroy")
    @patch("crabpot.cli._create_runtime")
    @patch("crabpot.config.load_config")
    def test_destroy_confirmed(self, mock_load, mock_create, mock_input, tmp_path):
        mock_runtime = MagicMock()
        mock_create.return_value = mock_runtime
        mock_load.return_value.target = "docker"
        args = argparse.Namespace(command="destroy")
        with patch("crabpot.cli.CONFIG_DIR", tmp_path):
            dispatch(args)
        mock_runtime.destroy.assert_called_once()

    @patch("builtins.input", return_value="no")
    def test_destroy_aborted(self, mock_input, capsys):
        args = argparse.Namespace(command="destroy")
        dispatch(args)


class TestCmdAlerts:
    def test_alerts_empty(self, tmp_path, capsys):
        args = argparse.Namespace(command="alerts", last=20, severity=None)
        with patch("crabpot.cli.DATA_DIR", tmp_path):
            dispatch(args)


class TestCmdTui:
    @patch("crabpot.tui.TUI")
    @patch("crabpot.cli._create_runtime")
    @patch("crabpot.config.load_config")
    def test_tui_launches(self, mock_load, mock_create, mock_tui_cls, tmp_path):
        mock_runtime = MagicMock()
        mock_create.return_value = mock_runtime
        args = argparse.Namespace(command="tui")
        with patch("crabpot.cli.DATA_DIR", tmp_path):
            dispatch(args)
        mock_tui_cls.assert_called_once()
        mock_tui_cls.return_value.run.assert_called_once()
