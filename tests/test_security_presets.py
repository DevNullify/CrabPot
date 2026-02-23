"""Tests for security_presets.py."""

from dataclasses import fields

import pytest

from crabpot.security_presets import (
    PRESETS,
    VALID_PRESET_NAMES,
    ResourceProfile,
    SecurityProfile,
    resolve_profile,
)


class TestSecurityProfile:
    def test_default_matches_standard(self):
        default = SecurityProfile()
        standard, _ = PRESETS["standard"]
        assert default == standard

    def test_all_fields_are_bool(self):
        for f in fields(SecurityProfile):
            assert f.type is bool, f"{f.name} should be bool"


class TestResourceProfile:
    def test_default_matches_standard(self):
        default = ResourceProfile()
        _, standard = PRESETS["standard"]
        assert default == standard


class TestPresets:
    def test_valid_preset_names(self):
        assert VALID_PRESET_NAMES == ("minimal", "standard", "paranoid")

    def test_minimal_all_off(self):
        sec, res = PRESETS["minimal"]
        for f in fields(SecurityProfile):
            assert getattr(sec, f.name) is False, f"minimal.{f.name} should be False"
        assert res.cpu_limit == "4"
        assert res.memory_limit == "4g"
        assert res.pids_limit == 500

    def test_standard_has_expected_on(self):
        sec, _ = PRESETS["standard"]
        assert sec.read_only_rootfs is True
        assert sec.drop_all_caps is True
        assert sec.seccomp_profile is True
        assert sec.egress_proxy is True
        assert sec.log_scanner is True
        assert sec.auto_pause_on_critical is True
        # Off in standard
        assert sec.process_watchdog is False
        assert sec.network_auditor is False
        assert sec.hardened_image is False

    def test_paranoid_all_on(self):
        sec, res = PRESETS["paranoid"]
        for f in fields(SecurityProfile):
            assert getattr(sec, f.name) is True, f"paranoid.{f.name} should be True"
        assert res.cpu_limit == "1"
        assert res.memory_limit == "1g"
        assert res.pids_limit == 100


class TestResolveProfile:
    def test_resolve_standard_no_overrides(self):
        sec, res = resolve_profile("standard")
        expected_sec, expected_res = PRESETS["standard"]
        assert sec == expected_sec
        assert res == expected_res

    def test_resolve_minimal(self):
        sec, res = resolve_profile("minimal")
        expected_sec, expected_res = PRESETS["minimal"]
        assert sec == expected_sec
        assert res == expected_res

    def test_resolve_paranoid(self):
        sec, res = resolve_profile("paranoid")
        expected_sec, expected_res = PRESETS["paranoid"]
        assert sec == expected_sec
        assert res == expected_res

    def test_override_single_security_feature(self):
        sec, _ = resolve_profile("minimal", overrides={"read_only_rootfs": True})
        assert sec.read_only_rootfs is True
        # Rest stays minimal (off)
        assert sec.drop_all_caps is False
        assert sec.seccomp_profile is False

    def test_override_none_values_ignored(self):
        sec, _ = resolve_profile("standard", overrides={"read_only_rootfs": None})
        # None means inherit from preset
        assert sec.read_only_rootfs is True

    def test_override_multiple_features(self):
        sec, _ = resolve_profile(
            "minimal",
            overrides={"read_only_rootfs": True, "seccomp_profile": True, "hardened_image": True},
        )
        assert sec.read_only_rootfs is True
        assert sec.seccomp_profile is True
        assert sec.hardened_image is True
        assert sec.drop_all_caps is False  # not overridden

    def test_override_turns_off_feature(self):
        sec, _ = resolve_profile("paranoid", overrides={"hardened_image": False})
        assert sec.hardened_image is False
        assert sec.process_watchdog is True  # not overridden

    def test_resource_overrides(self):
        _, res = resolve_profile("standard", resource_overrides={"cpu_limit": "4"})
        assert res.cpu_limit == "4"
        assert res.memory_limit == "2g"  # inherited

    def test_resource_override_none_ignored(self):
        _, res = resolve_profile("standard", resource_overrides={"cpu_limit": None})
        assert res.cpu_limit == "2"

    def test_resource_override_pids(self):
        _, res = resolve_profile("minimal", resource_overrides={"pids_limit": 300})
        assert res.pids_limit == 300
        assert res.memory_limit == "4g"

    def test_both_overrides(self):
        sec, res = resolve_profile(
            "minimal",
            overrides={"egress_proxy": True},
            resource_overrides={"memory_limit": "8g"},
        )
        assert sec.egress_proxy is True
        assert res.memory_limit == "8g"

    def test_invalid_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            resolve_profile("ultra")

    def test_invalid_security_override_raises(self):
        with pytest.raises(ValueError, match="Unknown security override"):
            resolve_profile("standard", overrides={"nonexistent_feature": True})

    def test_invalid_resource_override_raises(self):
        with pytest.raises(ValueError, match="Unknown resource override"):
            resolve_profile("standard", resource_overrides={"disk_limit": "10g"})

    def test_resolve_does_not_mutate_presets(self):
        original_sec, original_res = PRESETS["standard"]
        orig_ro = original_sec.read_only_rootfs

        resolve_profile("standard", overrides={"read_only_rootfs": False})

        assert original_sec.read_only_rootfs == orig_ro
