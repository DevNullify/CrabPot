"""YAML configuration loader/saver for CrabPot v2.

Provides the CrabPotConfig dataclass tree and functions to load, save,
and validate ~/.crabpot/crabpot.yml.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from crabpot.paths import CONFIG_FILE
from crabpot.security_presets import VALID_PRESET_NAMES

# ── Config dataclasses ─────────────────────────────────────────────────


@dataclass
class OpenClawConfig:
    """OpenClaw source and version settings."""

    source: str = "image"  # 'image' or 'build'
    image_tag: str = "latest"
    repo_url: str = "https://github.com/openclaw/openclaw.git"
    repo_ref: str = "main"


@dataclass
class SecurityConfig:
    """Security preset and per-feature overrides."""

    preset: str = "standard"
    overrides: Dict[str, Optional[bool]] = field(default_factory=dict)


@dataclass
class ResourceConfig:
    """Resource limit overrides (null = inherit from preset)."""

    cpu_limit: Optional[str] = None
    memory_limit: Optional[str] = None
    pids_limit: Optional[int] = None


@dataclass
class EgressConfig:
    """Egress proxy settings."""

    proxy_port: int = 9877


@dataclass
class DashboardConfig:
    """Dashboard settings."""

    port: int = 9876


@dataclass
class WSL2Config:
    """WSL2-specific settings."""

    distro_name: str = "CrabPot"
    base_image: str = "ubuntu:22.04"


@dataclass
class CrabPotConfig:
    """Top-level CrabPot configuration."""

    target: str = "docker"  # 'docker' or 'wsl2'
    openclaw: OpenClawConfig = field(default_factory=OpenClawConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    egress: EgressConfig = field(default_factory=EgressConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    wsl2: WSL2Config = field(default_factory=WSL2Config)


# ── Validation ─────────────────────────────────────────────────────────


def validate_config(config: CrabPotConfig) -> List[str]:
    """Validate a CrabPotConfig, returning a list of error messages (empty = valid)."""
    errors: List[str] = []

    if config.target not in ("docker", "wsl2"):
        errors.append(f"Invalid target '{config.target}'. Must be 'docker' or 'wsl2'.")

    if config.openclaw.source not in ("image", "build"):
        errors.append(
            f"Invalid openclaw.source '{config.openclaw.source}'. Must be 'image' or 'build'."
        )

    if config.security.preset not in VALID_PRESET_NAMES:
        errors.append(
            f"Invalid security.preset '{config.security.preset}'. "
            f"Must be one of: {', '.join(VALID_PRESET_NAMES)}."
        )

    from dataclasses import fields as dc_fields

    from crabpot.security_presets import SecurityProfile

    valid_security_keys = {f.name for f in dc_fields(SecurityProfile)}
    for key in config.security.overrides:
        if key not in valid_security_keys:
            errors.append(f"Unknown security override key: '{key}'.")

    if config.egress.proxy_port < 1 or config.egress.proxy_port > 65535:
        errors.append(f"Invalid egress.proxy_port: {config.egress.proxy_port}.")

    if config.dashboard.port < 1 or config.dashboard.port > 65535:
        errors.append(f"Invalid dashboard.port: {config.dashboard.port}.")

    return errors


# ── Serialisation helpers ──────────────────────────────────────────────


def _config_to_dict(config: CrabPotConfig) -> Dict[str, Any]:
    """Convert a CrabPotConfig to a plain dict suitable for YAML output."""
    return asdict(config)


def _dict_to_config(data: Dict[str, Any]) -> CrabPotConfig:
    """Build a CrabPotConfig from a plain dict (e.g. parsed YAML)."""
    if not isinstance(data, dict):
        return CrabPotConfig()

    openclaw_data = data.get("openclaw") or {}
    security_data = data.get("security") or {}
    resources_data = data.get("resources") or {}
    egress_data = data.get("egress") or {}
    dashboard_data = data.get("dashboard") or {}
    wsl2_data = data.get("wsl2") or {}

    return CrabPotConfig(
        target=data.get("target", "docker"),
        openclaw=OpenClawConfig(
            source=openclaw_data.get("source", "image"),
            image_tag=str(openclaw_data.get("image_tag", "latest")),
            repo_url=openclaw_data.get("repo_url", OpenClawConfig.repo_url),
            repo_ref=openclaw_data.get("repo_ref", "main"),
        ),
        security=SecurityConfig(
            preset=security_data.get("preset", "standard"),
            overrides=security_data.get("overrides") or {},
        ),
        resources=ResourceConfig(
            cpu_limit=resources_data.get("cpu_limit"),
            memory_limit=resources_data.get("memory_limit"),
            pids_limit=resources_data.get("pids_limit"),
        ),
        egress=EgressConfig(
            proxy_port=egress_data.get("proxy_port", 9877),
        ),
        dashboard=DashboardConfig(
            port=dashboard_data.get("port", 9876),
        ),
        wsl2=WSL2Config(
            distro_name=wsl2_data.get("distro_name", "CrabPot"),
            base_image=wsl2_data.get("base_image", "ubuntu:22.04"),
        ),
    )


# ── Public API ─────────────────────────────────────────────────────────


def load_config(config_path: Optional[Path] = None) -> CrabPotConfig:
    """Load CrabPot configuration from YAML.

    If the config file doesn't exist, returns defaults.
    """
    path = config_path or CONFIG_FILE
    if not path.exists():
        return CrabPotConfig()

    text = path.read_text()
    data = yaml.safe_load(text)
    return _dict_to_config(data)


def save_config(config: CrabPotConfig, config_path: Optional[Path] = None) -> None:
    """Save CrabPot configuration to YAML."""
    path = config_path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    data = _config_to_dict(config)
    text = yaml.dump(data, default_flow_style=False, sort_keys=False)
    path.write_text(text)


def default_config_yaml() -> str:
    """Return the default configuration as a YAML string with comments."""
    return """\
# CrabPot Configuration
# See: https://github.com/DevNullify/CrabPot#configuration

target: docker          # 'docker' or 'wsl2'

openclaw:
  source: image          # 'image' or 'build'
  image_tag: latest      # e.g. 'latest', 'v1.2.3'
  repo_url: https://github.com/openclaw/openclaw.git
  repo_ref: main         # branch/tag/commit

security:
  preset: standard       # 'minimal', 'standard', 'paranoid'
  overrides:             # null = inherit preset; true/false = explicit
    read_only_rootfs: null
    drop_all_caps: null
    seccomp_profile: null
    no_new_privileges: null
    resource_limits: null
    pid_limit: null
    egress_proxy: null
    secret_scanner: null
    process_watchdog: null
    log_scanner: null
    network_auditor: null
    hardened_image: null
    auto_pause_on_critical: null

resources:               # null = inherit preset
  cpu_limit: null
  memory_limit: null
  pids_limit: null

egress:
  proxy_port: 9877

dashboard:
  port: 9876

wsl2:                    # only used when target=wsl2
  distro_name: CrabPot
  base_image: ubuntu:22.04
"""
