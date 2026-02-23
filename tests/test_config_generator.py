"""Tests for config_generator.py."""

import json

import pytest

from crabpot.config_generator import ConfigGenerator
from crabpot.security_presets import ResourceProfile, resolve_profile


@pytest.fixture
def config_dir(tmp_path):
    """Provide a temporary config directory."""
    return tmp_path / "config"


@pytest.fixture
def generator(config_dir):
    """Provide a ConfigGenerator with temp directory (standard preset)."""
    return ConfigGenerator.from_defaults(config_dir=config_dir)


class TestConfigGenerator:
    def test_generate_all_creates_files(self, generator, config_dir):
        generator.generate_all()

        assert (config_dir / "docker-compose.yml").exists()
        assert (config_dir / "seccomp-profile.json").exists()
        assert (config_dir / ".env").exists()
        # Standard preset: no hardened image, so no Dockerfile
        assert not (config_dir / "Dockerfile.crabpot").exists()

    def test_seccomp_profile_valid_json(self, generator, config_dir):
        generator.generate_all()

        with open(config_dir / "seccomp-profile.json") as f:
            profile = json.load(f)

        assert profile["defaultAction"] == "SCMP_ACT_ERRNO"
        assert len(profile["syscalls"]) >= 2

        allowed = profile["syscalls"][0]
        assert allowed["action"] == "SCMP_ACT_ALLOW"
        assert "read" in allowed["names"]
        assert "write" in allowed["names"]

        blocked = profile["syscalls"][1]
        assert blocked["action"] == "SCMP_ACT_ERRNO"
        assert "mount" in blocked["names"]
        assert "ptrace" in blocked["names"]

    def test_compose_standard_preset_has_security(self, generator, config_dir):
        generator.generate_all()
        compose = (config_dir / "docker-compose.yml").read_text()

        assert "read_only: true" in compose
        assert "no-new-privileges:true" in compose
        assert "cap_drop:" in compose
        assert "ALL" in compose
        assert "NET_BIND_SERVICE" in compose
        assert "127.0.0.1:18789:18789" in compose
        assert 'enable_icc: "false"' in compose
        # Standard uses image: directly (no hardened Dockerfile)
        assert "image: openclaw/openclaw:latest" in compose

    def test_compose_uses_custom_limits(self, config_dir):
        sec, _ = resolve_profile("standard")
        res = ResourceProfile(cpu_limit="4", memory_limit="4g", pids_limit=500)
        gen = ConfigGenerator(
            config_dir=config_dir,
            security_profile=sec,
            resource_profile=res,
        )
        gen.generate_all()

        compose = (config_dir / "docker-compose.yml").read_text()
        assert '"4"' in compose
        assert "4g" in compose
        assert "500" in compose

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
        assert len(summary["files"]) >= 3

    def test_from_defaults_factory(self, config_dir):
        gen = ConfigGenerator.from_defaults(config_dir=config_dir)
        gen.generate_all()
        compose = (config_dir / "docker-compose.yml").read_text()
        assert "read_only: true" in compose


class TestMinimalPreset:
    def test_minimal_compose_no_security(self, config_dir):
        sec, res = resolve_profile("minimal")
        gen = ConfigGenerator(config_dir=config_dir, security_profile=sec, resource_profile=res)
        gen.generate_all()

        compose = (config_dir / "docker-compose.yml").read_text()

        assert "read_only: true" not in compose
        assert "cap_drop:" not in compose
        assert "no-new-privileges:true" not in compose
        assert "seccomp=" not in compose
        assert "deploy:" not in compose
        assert "pids_limit:" not in compose
        assert "HTTP_PROXY" not in compose
        # Uses image: directly
        assert "image: openclaw/openclaw:latest" in compose

    def test_minimal_no_seccomp_file(self, config_dir):
        sec, res = resolve_profile("minimal")
        gen = ConfigGenerator(config_dir=config_dir, security_profile=sec, resource_profile=res)
        gen.generate_all()

        assert not (config_dir / "seccomp-profile.json").exists()

    def test_minimal_no_dockerfile(self, config_dir):
        sec, res = resolve_profile("minimal")
        gen = ConfigGenerator(config_dir=config_dir, security_profile=sec, resource_profile=res)
        gen.generate_all()

        assert not (config_dir / "Dockerfile.crabpot").exists()


class TestParanoidPreset:
    def test_paranoid_generates_hardened_dockerfile(self, config_dir):
        sec, res = resolve_profile("paranoid")
        gen = ConfigGenerator(config_dir=config_dir, security_profile=sec, resource_profile=res)
        gen.generate_all()

        assert (config_dir / "Dockerfile.crabpot").exists()
        dockerfile = (config_dir / "Dockerfile.crabpot").read_text()
        assert "curl" in dockerfile
        assert "wget" in dockerfile
        assert "netcat" in dockerfile
        assert "USER 1000:1000" in dockerfile

    def test_paranoid_compose_uses_build(self, config_dir):
        sec, res = resolve_profile("paranoid")
        gen = ConfigGenerator(config_dir=config_dir, security_profile=sec, resource_profile=res)
        gen.generate_all()

        compose = (config_dir / "docker-compose.yml").read_text()
        assert "build:" in compose
        assert "dockerfile: Dockerfile.crabpot" in compose
        assert "image: openclaw/openclaw" not in compose

    def test_paranoid_compose_all_security(self, config_dir):
        sec, res = resolve_profile("paranoid")
        gen = ConfigGenerator(config_dir=config_dir, security_profile=sec, resource_profile=res)
        gen.generate_all()

        compose = (config_dir / "docker-compose.yml").read_text()
        assert "read_only: true" in compose
        assert "cap_drop:" in compose
        assert "no-new-privileges:true" in compose
        assert "seccomp=" in compose
        assert "deploy:" in compose
        assert "pids_limit:" in compose
        assert "HTTP_PROXY" in compose

    def test_paranoid_resource_limits(self, config_dir):
        sec, res = resolve_profile("paranoid")
        gen = ConfigGenerator(config_dir=config_dir, security_profile=sec, resource_profile=res)
        gen.generate_all()

        compose = (config_dir / "docker-compose.yml").read_text()
        assert '"1"' in compose  # cpu
        assert "1g" in compose  # memory
        assert "100" in compose  # pids


class TestCustomOpenClawTag:
    def test_image_tag_in_compose(self, config_dir):
        sec, res = resolve_profile("standard")
        gen = ConfigGenerator(
            config_dir=config_dir,
            security_profile=sec,
            resource_profile=res,
            openclaw_tag="v1.2.3",
        )
        gen.generate_all()

        compose = (config_dir / "docker-compose.yml").read_text()
        assert "openclaw/openclaw:v1.2.3" in compose

    def test_image_tag_in_hardened_dockerfile(self, config_dir):
        sec, res = resolve_profile("paranoid")
        gen = ConfigGenerator(
            config_dir=config_dir,
            security_profile=sec,
            resource_profile=res,
            openclaw_tag="v2.0.0",
        )
        gen.generate_all()

        dockerfile = (config_dir / "Dockerfile.crabpot").read_text()
        assert "openclaw/openclaw:v2.0.0" in dockerfile
