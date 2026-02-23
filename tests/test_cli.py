"""Tests for cli.py command handlers."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from crabpot.cli import dispatch


class TestDispatch:
    def test_unknown_command_exits(self, capsys):
        args = argparse.Namespace(command="nonexistent")
        with pytest.raises(SystemExit):
            dispatch(args)

    def test_none_command_does_not_crash(self):
        args = argparse.Namespace(command=None)
        with pytest.raises(SystemExit):
            dispatch(args)


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
        with patch("crabpot.cli.CONFIG_FILE", tmp_path / "crabpot.yml"), \
             patch("crabpot.cli.CONFIG_DIR", tmp_path / "config"), \
             patch("crabpot.cli.DATA_DIR", tmp_path / "data"):
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
    @patch("crabpot.docker_manager.docker")
    def test_stop_not_found(self, mock_docker, capsys):
        from docker.errors import NotFound

        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_client.containers.get.side_effect = NotFound("not found")
        args = argparse.Namespace(command="stop")
        dispatch(args)

    @patch("crabpot.docker_manager.docker")
    def test_stop_running(self, mock_docker):
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        container = MagicMock()
        container.status = "running"
        mock_client.containers.get.return_value = container

        args = argparse.Namespace(command="stop")
        dispatch(args)
        container.stop.assert_called_once()


class TestCmdPause:
    @patch("crabpot.docker_manager.docker")
    def test_pause(self, mock_docker):
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        container = MagicMock()
        container.status = "running"
        mock_client.containers.get.return_value = container

        args = argparse.Namespace(command="pause")
        dispatch(args)
        container.pause.assert_called_once()


class TestCmdResume:
    @patch("crabpot.docker_manager.docker")
    def test_resume(self, mock_docker):
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        container = MagicMock()
        container.status = "paused"
        mock_client.containers.get.return_value = container

        args = argparse.Namespace(command="resume")
        dispatch(args)
        container.unpause.assert_called_once()


class TestCmdStatus:
    @patch("crabpot.docker_manager.docker")
    def test_status_not_found(self, mock_docker, capsys):
        from docker.errors import NotFound

        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_client.containers.get.side_effect = NotFound("not found")

        args = argparse.Namespace(command="status")
        dispatch(args)


class TestCmdLogs:
    @patch("crabpot.docker_manager.docker")
    def test_logs_not_found(self, mock_docker):
        from docker.errors import NotFound

        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_client.containers.get.side_effect = NotFound("not found")

        args = argparse.Namespace(command="logs", follow=False, tail=10)
        with pytest.raises(SystemExit):
            dispatch(args)


class TestCmdAlerts:
    def test_alerts_empty(self, tmp_path, capsys):
        args = argparse.Namespace(command="alerts", last=20, severity=None)
        with patch("crabpot.cli.DATA_DIR", tmp_path):
            dispatch(args)
