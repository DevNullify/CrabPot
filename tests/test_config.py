"""Tests for config.py."""

import pytest
import yaml

from crabpot.config import (
    CrabPotConfig,
    DashboardConfig,
    EgressConfig,
    OpenClawConfig,
    ResourceConfig,
    SecurityConfig,
    WSL2Config,
    default_config_yaml,
    load_config,
    save_config,
    validate_config,
)


class TestCrabPotConfigDefaults:
    def test_default_target(self):
        config = CrabPotConfig()
        assert config.target == "docker"

    def test_default_openclaw(self):
        config = CrabPotConfig()
        assert config.openclaw.source == "image"
        assert config.openclaw.image_tag == "latest"

    def test_default_security(self):
        config = CrabPotConfig()
        assert config.security.preset == "standard"
        assert config.security.overrides == {}

    def test_default_resources_are_none(self):
        config = CrabPotConfig()
        assert config.resources.cpu_limit is None
        assert config.resources.memory_limit is None
        assert config.resources.pids_limit is None

    def test_default_egress_port(self):
        assert CrabPotConfig().egress.proxy_port == 9877

    def test_default_dashboard_port(self):
        assert CrabPotConfig().dashboard.port == 9876

    def test_default_wsl2(self):
        config = CrabPotConfig()
        assert config.wsl2.distro_name == "CrabPot"
        assert config.wsl2.base_image == "ubuntu:22.04"


class TestValidateConfig:
    def test_valid_default(self):
        errors = validate_config(CrabPotConfig())
        assert errors == []

    def test_invalid_target(self):
        config = CrabPotConfig(target="kubernetes")
        errors = validate_config(config)
        assert any("target" in e for e in errors)

    def test_invalid_source(self):
        config = CrabPotConfig(openclaw=OpenClawConfig(source="tarball"))
        errors = validate_config(config)
        assert any("source" in e for e in errors)

    def test_invalid_preset(self):
        config = CrabPotConfig(security=SecurityConfig(preset="ultra"))
        errors = validate_config(config)
        assert any("preset" in e for e in errors)

    def test_invalid_security_override_key(self):
        config = CrabPotConfig(
            security=SecurityConfig(overrides={"bogus_key": True})
        )
        errors = validate_config(config)
        assert any("bogus_key" in e for e in errors)

    def test_valid_security_override_key(self):
        config = CrabPotConfig(
            security=SecurityConfig(overrides={"read_only_rootfs": True})
        )
        errors = validate_config(config)
        assert errors == []

    def test_invalid_egress_port(self):
        config = CrabPotConfig(egress=EgressConfig(proxy_port=0))
        errors = validate_config(config)
        assert any("proxy_port" in e for e in errors)

    def test_invalid_dashboard_port(self):
        config = CrabPotConfig(dashboard=DashboardConfig(port=99999))
        errors = validate_config(config)
        assert any("dashboard.port" in e for e in errors)

    def test_multiple_errors(self):
        config = CrabPotConfig(
            target="bad",
            openclaw=OpenClawConfig(source="bad"),
        )
        errors = validate_config(config)
        assert len(errors) >= 2


class TestSaveAndLoad:
    def test_round_trip(self, tmp_path):
        config = CrabPotConfig(
            target="wsl2",
            openclaw=OpenClawConfig(image_tag="v1.2.3"),
            security=SecurityConfig(
                preset="paranoid",
                overrides={"hardened_image": False},
            ),
            resources=ResourceConfig(cpu_limit="4"),
        )
        path = tmp_path / "crabpot.yml"
        save_config(config, config_path=path)
        loaded = load_config(config_path=path)

        assert loaded.target == "wsl2"
        assert loaded.openclaw.image_tag == "v1.2.3"
        assert loaded.security.preset == "paranoid"
        assert loaded.security.overrides == {"hardened_image": False}
        assert loaded.resources.cpu_limit == "4"

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "crabpot.yml"
        save_config(CrabPotConfig(), config_path=path)
        assert path.exists()

    def test_load_nonexistent_returns_defaults(self, tmp_path):
        config = load_config(config_path=tmp_path / "missing.yml")
        assert config == CrabPotConfig()

    def test_load_empty_file_returns_defaults(self, tmp_path):
        path = tmp_path / "empty.yml"
        path.write_text("")
        config = load_config(config_path=path)
        assert config.target == "docker"
        assert config.security.preset == "standard"

    def test_load_partial_config(self, tmp_path):
        path = tmp_path / "partial.yml"
        path.write_text("target: wsl2\nsecurity:\n  preset: paranoid\n")
        config = load_config(config_path=path)
        assert config.target == "wsl2"
        assert config.security.preset == "paranoid"
        assert config.openclaw.source == "image"  # defaults

    def test_saved_file_is_valid_yaml(self, tmp_path):
        path = tmp_path / "crabpot.yml"
        save_config(CrabPotConfig(), config_path=path)
        data = yaml.safe_load(path.read_text())
        assert data["target"] == "docker"
        assert data["security"]["preset"] == "standard"

    def test_image_tag_preserved_as_string(self, tmp_path):
        """Ensure numeric image tags like 'latest' or '1.0' stay as strings."""
        config = CrabPotConfig(openclaw=OpenClawConfig(image_tag="1.0"))
        path = tmp_path / "crabpot.yml"
        save_config(config, config_path=path)
        loaded = load_config(config_path=path)
        assert loaded.openclaw.image_tag == "1.0"
        assert isinstance(loaded.openclaw.image_tag, str)

    def test_resources_none_round_trip(self, tmp_path):
        config = CrabPotConfig()
        path = tmp_path / "crabpot.yml"
        save_config(config, config_path=path)
        loaded = load_config(config_path=path)
        assert loaded.resources.cpu_limit is None
        assert loaded.resources.memory_limit is None
        assert loaded.resources.pids_limit is None


class TestDefaultConfigYaml:
    def test_is_valid_yaml(self):
        text = default_config_yaml()
        data = yaml.safe_load(text)
        assert data["target"] == "docker"

    def test_contains_all_sections(self):
        text = default_config_yaml()
        for section in ["target", "openclaw", "security", "resources", "egress", "dashboard", "wsl2"]:
            assert section in text

    def test_loadable_as_config(self):
        text = default_config_yaml()
        data = yaml.safe_load(text)
        from crabpot.config import _dict_to_config
        config = _dict_to_config(data)
        assert config.target == "docker"
        assert config.security.preset == "standard"
