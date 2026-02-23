"""Tests for egress_policy.py — domain allowlist, secret scanner, and deobfuscation."""

import base64

import pytest

from crabpot.egress_policy import (
    Decision,
    EgressPolicy,
    _deobfuscate_layers,
    _shannon_entropy,
    _try_decode_base64,
    _try_decode_hex,
    _try_url_decode,
)


@pytest.fixture
def policy_file(tmp_path):
    """Create a test policy file."""
    p = tmp_path / "egress-allowlist.txt"
    p.write_text(
        "# Test allowlist\n"
        "api.openai.com\n"
        "*.anthropic.com\n"
        "registry.npmjs.org\n"
        "\n"
        "!evil.example.com\n"
        "!*.attacker.net\n"
    )
    return p


@pytest.fixture
def policy(policy_file):
    return EgressPolicy(policy_path=policy_file)


class TestDomainMatching:
    def test_exact_match_allowed(self, policy):
        assert policy.check_domain("api.openai.com") == Decision.ALLOW

    def test_wildcard_match_allowed(self, policy):
        assert policy.check_domain("api.anthropic.com") == Decision.ALLOW
        assert policy.check_domain("sub.anthropic.com") == Decision.ALLOW

    def test_wildcard_base_domain_allowed(self, policy):
        assert policy.check_domain("anthropic.com") == Decision.ALLOW

    def test_unknown_domain_pending(self, policy):
        assert policy.check_domain("evil.xyz") == Decision.PENDING

    def test_unknown_domain_deny_mode(self, policy_file):
        policy = EgressPolicy(policy_path=policy_file, unknown_action="deny")
        assert policy.check_domain("evil.xyz") == Decision.DENY

    def test_explicit_blocklist_override(self, policy):
        assert policy.check_domain("evil.example.com") == Decision.DENY

    def test_wildcard_blocklist(self, policy):
        assert policy.check_domain("sub.attacker.net") == Decision.DENY

    def test_default_blocklist_included(self, policy):
        assert policy.check_domain("webhook.site") == Decision.DENY
        assert policy.check_domain("foo.ngrok.io") == Decision.DENY

    def test_case_insensitive(self, policy):
        assert policy.check_domain("API.OPENAI.COM") == Decision.ALLOW

    def test_blocklist_takes_priority(self, tmp_path):
        """Blocklist should override allowlist for the same domain."""
        p = tmp_path / "policy.txt"
        p.write_text("*.example.com\n!evil.example.com\n")
        policy = EgressPolicy(policy_path=p)
        assert policy.check_domain("good.example.com") == Decision.ALLOW
        assert policy.check_domain("evil.example.com") == Decision.DENY


class TestSessionApprovals:
    def test_session_approve(self, policy):
        assert policy.check_domain("newsite.com") == Decision.PENDING
        policy.session_approve("newsite.com")
        assert policy.check_domain("newsite.com") == Decision.ALLOW

    def test_session_deny(self, policy):
        policy.session_deny("badsite.com")
        assert policy.check_domain("badsite.com") == Decision.DENY

    def test_deny_overrides_approve(self, policy):
        policy.session_approve("flip.com")
        assert policy.check_domain("flip.com") == Decision.ALLOW
        policy.session_deny("flip.com")
        assert policy.check_domain("flip.com") == Decision.DENY


class TestPermanentAllowlist:
    def test_add_permanent(self, policy):
        policy.add_permanent("newdomain.com")
        assert "newdomain.com" in policy.get_allowlist()
        assert policy.check_domain("newdomain.com") == Decision.ALLOW

    def test_remove_permanent(self, policy):
        policy.remove_permanent("api.openai.com")
        assert "api.openai.com" not in policy.get_allowlist()

    def test_save_and_reload(self, policy_file):
        policy = EgressPolicy(policy_path=policy_file)
        policy.add_permanent("saved.example.com")

        # Reload from file
        reloaded = EgressPolicy(policy_path=policy_file)
        assert reloaded.check_domain("saved.example.com") == Decision.ALLOW


class TestAuditLog:
    def test_log_attempt(self, policy):
        policy.log_attempt("example.com", 443, "CONNECT", "allow")
        log = policy.get_audit_log()
        assert len(log) == 1
        assert log[0]["domain"] == "example.com"
        assert log[0]["decision"] == "allow"

    def test_audit_bounded(self, policy):
        for i in range(6000):
            policy.log_attempt(f"d{i}.com", 443, "CONNECT", "allow")
        # Trim fires at >5000, keeping last 2500, then up to 1000 more added = 3500 max
        assert len(policy.get_audit_log(last=10000)) <= 4000


class TestSecretScanner:
    def test_detect_openai_key(self, policy):
        content = "Authorization: Bearer sk-abcdefghijklmnopqrstuvwxyz1234567890"
        findings = policy.scan_for_secrets(content)
        assert len(findings) > 0

    def test_detect_anthropic_key(self, policy):
        content = "key=sk-ant-abcdefghijklmnopqrstuvwxyz1234567890"
        findings = policy.scan_for_secrets(content)
        assert len(findings) > 0

    def test_detect_aws_key(self, policy):
        content = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"
        findings = policy.scan_for_secrets(content)
        assert len(findings) > 0

    def test_detect_github_pat(self, policy):
        content = "token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        findings = policy.scan_for_secrets(content)
        assert len(findings) > 0

    def test_no_false_positive_on_safe_content(self, policy):
        content = "Hello world, this is a normal message."
        findings = policy.scan_for_secrets(content)
        assert len(findings) == 0

    def test_detect_base64_encoded_secret(self, policy):
        """Secrets encoded in base64 should still be caught."""
        secret = "sk-abcdefghijklmnopqrstuvwxyz1234567890"
        encoded = base64.b64encode(secret.encode()).decode()
        findings = policy.scan_for_secrets(encoded)
        # Should detect via deobfuscation or high entropy
        assert len(findings) > 0

    def test_detect_private_ip(self, policy):
        content = "connecting to 192.168.1.100:8080"
        findings = policy.scan_for_secrets(content)
        assert any("sensitive_data" in f for f in findings)

    def test_detect_ssh_key_marker(self, policy):
        content = "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."
        findings = policy.scan_for_secrets(content)
        assert any("sensitive_data" in f for f in findings)

    def test_detect_high_entropy_string(self, policy):
        # Random-looking string with high entropy
        content = "token=aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5zA7bC9"
        findings = policy.scan_for_secrets(content)
        assert any("high_entropy" in f for f in findings)


class TestDeobfuscation:
    def test_base64_decode(self):
        original = "this is a secret api key value"
        encoded = base64.b64encode(original.encode()).decode()
        decoded = _try_decode_base64(encoded)
        assert decoded == original

    def test_hex_decode(self):
        original = "this is a secret key"
        hex_str = original.encode().hex()
        decoded = _try_decode_hex(hex_str)
        assert decoded == original

    def test_url_decode(self):
        decoded = _try_url_decode("sk%2Dant%2Dabcdefghijklmnop")
        assert decoded == "sk-ant-abcdefghijklmnop"

    def test_invalid_base64_returns_empty(self):
        assert _try_decode_base64("not-valid!!") == ""

    def test_deobfuscate_layers_finds_base64(self):
        secret = "sk-abcdefghijklmnopqrstuvwxyz1234567890"
        encoded = base64.b64encode(secret.encode()).decode()
        content = f"data={encoded}"
        variants = _deobfuscate_layers(content)
        assert any(secret in v for v in variants)

    def test_dot_separated_reassembly(self):
        content = "s.k.-.a.n.t.-.a.b.c.d.e.f.g.h.i.j.k.l.m.n.o.p.q.r.s.t.u"
        variants = _deobfuscate_layers(content)
        assert any("sk-ant-" in v for v in variants)


class TestShannonEntropy:
    def test_low_entropy_text(self):
        assert _shannon_entropy("aaaaaaaaaa") < 1.0

    def test_high_entropy_random(self):
        # Mix of many different chars
        s = "aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1v"
        assert _shannon_entropy(s) > 4.0

    def test_empty_string(self):
        assert _shannon_entropy("") == 0.0


class TestPolicyWithoutFile:
    def test_no_file_uses_defaults(self):
        policy = EgressPolicy()
        # Default blocklist should work
        assert policy.check_domain("webhook.site") == Decision.DENY
        # Unknown domains default to pending
        assert policy.check_domain("unknown.com") == Decision.PENDING

    def test_nonexistent_file(self, tmp_path):
        policy = EgressPolicy(policy_path=tmp_path / "nonexistent.txt")
        assert policy.check_domain("example.com") == Decision.PENDING
