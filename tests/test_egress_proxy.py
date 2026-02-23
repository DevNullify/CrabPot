"""Tests for egress_proxy.py — proxy server lifecycle and policy enforcement."""

import socket
import time
from unittest.mock import MagicMock

import pytest

from crabpot.action_gate import ActionGate
from crabpot.egress_policy import EgressPolicy
from crabpot.egress_proxy import EgressProxy


@pytest.fixture
def policy(tmp_path):
    p = tmp_path / "policy.txt"
    p.write_text("api.openai.com\n*.allowed.com\n!blocked.example.com\n")
    return EgressPolicy(policy_path=p)


@pytest.fixture
def gate(policy):
    return ActionGate(egress_policy=policy, alert_dispatcher=MagicMock(), timeout=1)


@pytest.fixture
def proxy(policy, gate):
    # Use a random high port to avoid conflicts
    proxy = EgressProxy(policy=policy, gate=gate, port=0)
    return proxy


class TestProxyLifecycle:
    def test_start_and_stop(self, policy, gate):
        proxy = EgressProxy(policy=policy, gate=gate, host="127.0.0.1", port=19877)
        proxy.start()
        assert proxy.is_running
        time.sleep(0.2)
        proxy.stop()
        assert not proxy.is_running

    def test_proxy_accepts_connections(self, policy, gate):
        proxy = EgressProxy(policy=policy, gate=gate, host="127.0.0.1", port=19878)
        proxy.start()
        time.sleep(0.2)
        try:
            sock = socket.create_connection(("127.0.0.1", 19878), timeout=2)
            sock.close()
        finally:
            proxy.stop()


class TestPolicyEnforcement:
    def test_allowed_domain_connect(self, policy, gate):
        """CONNECT to an allowed domain gets 200 (or 502 if no upstream)."""
        proxy = EgressProxy(policy=policy, gate=gate, host="127.0.0.1", port=19879)
        proxy.start()
        time.sleep(0.2)
        try:
            sock = socket.create_connection(("127.0.0.1", 19879), timeout=2)
            sock.sendall(b"CONNECT api.openai.com:443 HTTP/1.1\r\nHost: api.openai.com\r\n\r\n")
            response = sock.recv(4096).decode()
            # Should get 200 (connection established) or 502 (can't reach upstream)
            # Both mean the policy allowed it through
            assert "200" in response or "502" in response
            sock.close()
        finally:
            proxy.stop()

    def test_blocked_domain_connect(self, policy, gate):
        """CONNECT to a blocked domain gets 403."""
        proxy = EgressProxy(policy=policy, gate=gate, host="127.0.0.1", port=19880)
        proxy.start()
        time.sleep(0.2)
        try:
            sock = socket.create_connection(("127.0.0.1", 19880), timeout=2)
            sock.sendall(
                b"CONNECT blocked.example.com:443 HTTP/1.1\r\nHost: blocked.example.com\r\n\r\n"
            )
            response = sock.recv(4096).decode()
            assert "403" in response
            sock.close()
        finally:
            proxy.stop()

    def test_default_blocked_domain(self, policy, gate):
        """CONNECT to a known-bad domain (ngrok) gets 403."""
        proxy = EgressProxy(policy=policy, gate=gate, host="127.0.0.1", port=19881)
        proxy.start()
        time.sleep(0.2)
        try:
            sock = socket.create_connection(("127.0.0.1", 19881), timeout=2)
            sock.sendall(b"CONNECT evil.ngrok.io:443 HTTP/1.1\r\nHost: evil.ngrok.io\r\n\r\n")
            response = sock.recv(4096).decode()
            assert "403" in response
            sock.close()
        finally:
            proxy.stop()

    def test_audit_logging(self, policy, gate):
        """Proxy logs connection attempts to the policy audit trail."""
        proxy = EgressProxy(policy=policy, gate=gate, host="127.0.0.1", port=19882)
        proxy.start()
        time.sleep(0.2)
        try:
            sock = socket.create_connection(("127.0.0.1", 19882), timeout=2)
            sock.sendall(b"CONNECT api.openai.com:443 HTTP/1.1\r\nHost: api.openai.com\r\n\r\n")
            sock.recv(4096)
            sock.close()
            time.sleep(0.2)

            log = policy.get_audit_log()
            assert len(log) >= 1
            assert log[0]["domain"] == "api.openai.com"
        finally:
            proxy.stop()
