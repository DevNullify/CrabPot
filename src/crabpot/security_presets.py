"""Security presets and profile resolution for CrabPot v2.

Defines the SecurityProfile and ResourceProfile dataclasses, three named
presets (minimal, standard, paranoid), and a resolve_profile() function
that merges a preset with user-supplied overrides.
"""

from dataclasses import asdict, dataclass, fields
from typing import Any, Optional


@dataclass
class SecurityProfile:
    """Boolean feature flags for every security layer."""

    read_only_rootfs: bool = True
    drop_all_caps: bool = True
    seccomp_profile: bool = True
    no_new_privileges: bool = True
    resource_limits: bool = True
    pid_limit: bool = True
    egress_proxy: bool = True
    secret_scanner: bool = True
    process_watchdog: bool = False
    log_scanner: bool = True
    network_auditor: bool = False
    hardened_image: bool = False
    auto_pause_on_critical: bool = True


@dataclass
class ResourceProfile:
    """Resource constraint values."""

    cpu_limit: str = "2"
    memory_limit: str = "2g"
    pids_limit: int = 200


# ── Named presets ──────────────────────────────────────────────────────

PRESETS: dict[str, tuple[SecurityProfile, ResourceProfile]] = {
    "minimal": (
        SecurityProfile(
            read_only_rootfs=False,
            drop_all_caps=False,
            seccomp_profile=False,
            no_new_privileges=False,
            resource_limits=False,
            pid_limit=False,
            egress_proxy=False,
            secret_scanner=False,
            process_watchdog=False,
            log_scanner=False,
            network_auditor=False,
            hardened_image=False,
            auto_pause_on_critical=False,
        ),
        ResourceProfile(cpu_limit="4", memory_limit="4g", pids_limit=500),
    ),
    "standard": (
        SecurityProfile(
            read_only_rootfs=True,
            drop_all_caps=True,
            seccomp_profile=True,
            no_new_privileges=True,
            resource_limits=True,
            pid_limit=True,
            egress_proxy=True,
            secret_scanner=True,
            process_watchdog=False,
            log_scanner=True,
            network_auditor=False,
            hardened_image=False,
            auto_pause_on_critical=True,
        ),
        ResourceProfile(cpu_limit="2", memory_limit="2g", pids_limit=200),
    ),
    "paranoid": (
        SecurityProfile(
            read_only_rootfs=True,
            drop_all_caps=True,
            seccomp_profile=True,
            no_new_privileges=True,
            resource_limits=True,
            pid_limit=True,
            egress_proxy=True,
            secret_scanner=True,
            process_watchdog=True,
            log_scanner=True,
            network_auditor=True,
            hardened_image=True,
            auto_pause_on_critical=True,
        ),
        ResourceProfile(cpu_limit="1", memory_limit="1g", pids_limit=100),
    ),
}

VALID_PRESET_NAMES = tuple(PRESETS.keys())


def resolve_profile(
    preset_name: str = "standard",
    overrides: Optional[dict[str, Any]] = None,
    resource_overrides: Optional[dict[str, Any]] = None,
) -> tuple[SecurityProfile, ResourceProfile]:
    """Merge a named preset with user-supplied overrides.

    Args:
        preset_name: One of 'minimal', 'standard', 'paranoid'.
        overrides: Dict mapping SecurityProfile field names to bool values.
            Keys with None values are ignored (inherit from preset).
        resource_overrides: Dict mapping ResourceProfile field names to values.
            Keys with None values are ignored (inherit from preset).

    Returns:
        A (SecurityProfile, ResourceProfile) tuple with overrides applied.

    Raises:
        ValueError: If preset_name is not recognised or override keys are invalid.
    """
    if preset_name not in PRESETS:
        raise ValueError(
            f"Unknown preset '{preset_name}'. Valid presets: {', '.join(VALID_PRESET_NAMES)}"
        )

    base_security, base_resources = PRESETS[preset_name]

    # Deep-copy via asdict → reconstruct
    security_dict = asdict(base_security)
    resource_dict = asdict(base_resources)

    security_field_names = {f.name for f in fields(SecurityProfile)}
    resource_field_names = {f.name for f in fields(ResourceProfile)}

    if overrides:
        for key, value in overrides.items():
            if key not in security_field_names:
                raise ValueError(
                    f"Unknown security override '{key}'. "
                    f"Valid keys: {', '.join(sorted(security_field_names))}"
                )
            if value is not None:
                security_dict[key] = bool(value)

    if resource_overrides:
        for key, value in resource_overrides.items():
            if key not in resource_field_names:
                raise ValueError(
                    f"Unknown resource override '{key}'. "
                    f"Valid keys: {', '.join(sorted(resource_field_names))}"
                )
            if value is not None:
                resource_dict[key] = value

    return SecurityProfile(**security_dict), ResourceProfile(**resource_dict)
