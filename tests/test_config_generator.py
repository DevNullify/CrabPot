"""Tests for config_generator.py."""

import json
import tempfile
from pathlib import Path

import pytest

from crabpot.config_generator import ConfigGenerator


@pytest.fixture
def config_dir(tmp_path):
    """Provide a temporary config directory."""
    return tmp_path / "config"


@pytest.fixture
def generator(config_dir):
    """Provide a ConfigGenerator with temp directory."""
    return ConfigGenerator(config_dir=config_dir)


class TestConfigGenerator:
    def test_generate_all_creates_files(self, generator, config_dir):
        generator.generate_all()

        assert (config_dir / "docker-compose.yml").exists()
        assert (config_dir / "Dockerfile.crabpot").exists()
        assert (config_dir / "seccomp-profile.json").exists()
        assert (config_dir / ".env").exists()

    def test_seccomp_profile_valid_json(self, generator, config_dir):
        generator.generate_all()

        with open(config_dir / "seccomp-profile.json") as f:
            profile = json.load(f)

        assert profile["defaultAction"] == "SCMP_ACT_ERRNO"
        assert len(profile["syscalls"]) >= 2

        # Check that allowed syscalls exist
        allowed = profile["syscalls"][0]
        assert allowed["action"] == "SCMP_ACT_ALLOW"
        assert "read" in allowed["names"]
        assert "write" in allowed["names"]

        # Check that blocked syscalls exist
        blocked = profile["syscalls"][1]
        assert blocked["action"] == "SCMP_ACT_ERRNO"
        assert "mount" in blocked["names"]
        assert "ptrace" in blocked["names"]

    def test_compose_contains_security_settings(self, generator, config_dir):
        generator.generate_all()

        compose = (config_dir / "docker-compose.yml").read_text()

        assert "read_only: true" in compose
        assert "no-new-privileges:true" in compose
        assert "cap_drop:" in compose
        assert "ALL" in compose
        assert "NET_BIND_SERVICE" in compose
        assert "127.0.0.1:18789:18789" in compose
        assert 'enable_icc: "false"' in compose

    def test_compose_uses_custom_limits(self, config_dir):
        gen = ConfigGenerator(
            config_dir=config_dir,
            cpu_limit="4",
            memory_limit="4g",
            pids_limit=500,
        )
        gen.generate_all()

        compose = (config_dir / "docker-compose.yml").read_text()
        assert '"4"' in compose  # cpu limit
        assert "4g" in compose   # memory limit
        assert "500" in compose  # pids limit

    def test_dockerfile_removes_dangerous_binaries(self, generator, config_dir):
        generator.generate_all()

        dockerfile = (config_dir / "Dockerfile.crabpot").read_text()

        assert "curl" in dockerfile
        assert "wget" in dockerfile
        assert "netcat" in dockerfile
        assert "ssh" in dockerfile
        assert "USER 1000:1000" in dockerfile

    def test_env_file_not_overwritten(self, generator, config_dir):
        config_dir.mkdir(parents=True, exist_ok=True)
        env_path = config_dir / ".env"
        env_path.write_text("MY_KEY=secret\n")

        generator.generate_all()

        assert env_path.read_text() == "MY_KEY=secret\n"

    def test_get_config_summary(self, generator, config_dir):
        generator.generate_all()

        summary = generator.get_config_summary()

        assert summary["cpu_limit"] == "2"
        assert summary["memory_limit"] == "2g"
        assert summary["pids_limit"] == 200
        assert len(summary["files"]) >= 4
