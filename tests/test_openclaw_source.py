"""Tests for openclaw_source.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from crabpot.config import OpenClawConfig
from crabpot.openclaw_source import OpenClawSource


@pytest.fixture
def build_dir(tmp_path):
    return tmp_path / "build"


class TestImageMode:
    def test_resolve_docker_pull(self, build_dir):
        config = OpenClawConfig(source="image", image_tag="latest")
        source = OpenClawSource(config, build_base=build_dir)
        result = source.resolve_for_docker()

        assert result["mode"] == "pull"
        assert result["image"] == "openclaw/openclaw:latest"

    def test_resolve_docker_pull_custom_tag(self, build_dir):
        config = OpenClawConfig(source="image", image_tag="v1.2.3")
        source = OpenClawSource(config, build_base=build_dir)
        result = source.resolve_for_docker()

        assert result["image"] == "openclaw/openclaw:v1.2.3"

    def test_resolve_wsl2_extract(self, build_dir):
        config = OpenClawConfig(source="image", image_tag="latest")
        source = OpenClawSource(config, build_base=build_dir)
        result = source.resolve_for_wsl2()

        assert result["mode"] == "extract"
        assert result["image"] == "openclaw/openclaw:latest"

    def test_image_ref_property(self, build_dir):
        config = OpenClawConfig(source="image", image_tag="v2.0.0")
        source = OpenClawSource(config, build_base=build_dir)
        assert source.image_ref == "openclaw/openclaw:v2.0.0"


class TestBuildMode:
    @patch("crabpot.openclaw_source.subprocess.run")
    def test_resolve_docker_build_clones_repo(self, mock_run, build_dir):
        mock_run.return_value = MagicMock(returncode=0)
        config = OpenClawConfig(
            source="build",
            repo_url="https://github.com/openclaw/openclaw.git",
            repo_ref="main",
        )
        source = OpenClawSource(config, build_base=build_dir)
        result = source.resolve_for_docker()

        assert result["mode"] == "build"
        assert "openclaw" in result["context"]

        # Should have called git clone and git checkout
        calls = mock_run.call_args_list
        assert any("clone" in str(c) for c in calls)
        assert any("checkout" in str(c) for c in calls)

    @patch("crabpot.openclaw_source.subprocess.run")
    def test_resolve_docker_build_updates_existing(self, mock_run, build_dir):
        mock_run.return_value = MagicMock(returncode=0)

        # Simulate existing repo
        repo_dir = build_dir / "openclaw"
        repo_dir.mkdir(parents=True)
        (repo_dir / ".git").mkdir()

        config = OpenClawConfig(source="build", repo_ref="v1.0.0")
        source = OpenClawSource(config, build_base=build_dir)
        result = source.resolve_for_docker()

        assert result["mode"] == "build"

        # Should have called fetch + checkout (not clone)
        calls = mock_run.call_args_list
        assert any("fetch" in str(c) for c in calls)
        assert any("checkout" in str(c) for c in calls)
        assert not any("clone" in str(c) for c in calls)

    @patch("crabpot.openclaw_source.subprocess.run")
    def test_resolve_wsl2_build(self, mock_run, build_dir):
        mock_run.return_value = MagicMock(returncode=0)
        config = OpenClawConfig(source="build", repo_ref="develop")
        source = OpenClawSource(config, build_base=build_dir)
        result = source.resolve_for_wsl2()

        assert result["mode"] == "build"
        assert "openclaw" in result["repo_dir"]

    @patch("crabpot.openclaw_source.subprocess.run")
    def test_checkout_uses_configured_ref(self, mock_run, build_dir):
        mock_run.return_value = MagicMock(returncode=0)
        config = OpenClawConfig(source="build", repo_ref="v2.0.0-rc1")
        source = OpenClawSource(config, build_base=build_dir)
        source.resolve_for_docker()

        # Find the checkout call by inspecting the first positional arg (the cmd list)
        checkout_calls = [
            c for c in mock_run.call_args_list
            if c[0][0][1] == "checkout"
        ]
        assert len(checkout_calls) >= 1
        assert "v2.0.0-rc1" in checkout_calls[0][0][0]

    @patch("crabpot.openclaw_source.subprocess.run")
    def test_clone_uses_configured_url(self, mock_run, build_dir):
        mock_run.return_value = MagicMock(returncode=0)
        custom_url = "https://github.com/myorg/openclaw-fork.git"
        config = OpenClawConfig(source="build", repo_url=custom_url)
        source = OpenClawSource(config, build_base=build_dir)
        source.resolve_for_docker()

        clone_calls = [
            c for c in mock_run.call_args_list
            if "clone" in str(c)
        ]
        assert len(clone_calls) >= 1
        assert custom_url in str(clone_calls[0])

    @patch("crabpot.openclaw_source.subprocess.run")
    def test_build_creates_build_dir(self, mock_run, build_dir):
        mock_run.return_value = MagicMock(returncode=0)
        assert not build_dir.exists()

        config = OpenClawConfig(source="build")
        source = OpenClawSource(config, build_base=build_dir)
        source.resolve_for_docker()

        assert build_dir.exists()

    @patch("crabpot.openclaw_source.subprocess.run")
    def test_clone_failure_raises(self, mock_run, build_dir):
        import subprocess as sp
        mock_run.side_effect = sp.CalledProcessError(1, "git clone")
        config = OpenClawConfig(source="build")
        source = OpenClawSource(config, build_base=build_dir)

        with pytest.raises(sp.CalledProcessError):
            source.resolve_for_docker()
