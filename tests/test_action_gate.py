"""Tests for action_gate.py — human-in-the-loop approval system."""

import threading
import time
from unittest.mock import MagicMock

import pytest

from crabpot.action_gate import ActionGate, PendingRequest
from crabpot.egress_policy import EgressPolicy


@pytest.fixture
def policy():
    return EgressPolicy()


@pytest.fixture
def gate(policy):
    alerts = MagicMock()
    return ActionGate(egress_policy=policy, alert_dispatcher=alerts, timeout=2)


class TestPendingRequest:
    def test_approve_unblocks_wait(self):
        req = PendingRequest(domain="example.com", port=443)

        def approver():
            time.sleep(0.1)
            req.approve()

        threading.Thread(target=approver).start()
        assert req.wait(timeout=5) is True

    def test_deny_unblocks_wait(self):
        req = PendingRequest(domain="example.com", port=443)

        def denier():
            time.sleep(0.1)
            req.deny()

        threading.Thread(target=denier).start()
        assert req.wait(timeout=5) is False

    def test_timeout_returns_false(self):
        req = PendingRequest(domain="example.com", port=443)
        assert req.wait(timeout=0.2) is False


class TestActionGate:
    def test_approve_pending_domain(self, gate):
        result = [None]

        def requester():
            result[0] = gate.request_approval("newsite.com", 443)

        t = threading.Thread(target=requester)
        t.start()
        time.sleep(0.2)  # Let the request register

        assert len(gate.get_pending()) == 1
        gate.approve("newsite.com")
        t.join(timeout=5)

        assert result[0] is True

    def test_deny_pending_domain(self, gate):
        result = [None]

        def requester():
            result[0] = gate.request_approval("badsite.com", 443)

        t = threading.Thread(target=requester)
        t.start()
        time.sleep(0.2)

        gate.deny("badsite.com")
        t.join(timeout=5)

        assert result[0] is False

    def test_timeout_denies(self, gate):
        # Gate has timeout=2
        result = gate.request_approval("slowsite.com", 443)
        assert result is False

    def test_approve_permanent_adds_to_policy(self, gate, policy):
        result = [None]

        def requester():
            result[0] = gate.request_approval("perm.com", 443)

        t = threading.Thread(target=requester)
        t.start()
        time.sleep(0.2)

        gate.approve("perm.com", permanent=True)
        t.join(timeout=5)

        assert result[0] is True
        assert "perm.com" in policy.get_allowlist()

    def test_get_pending_snapshot(self, gate):
        def requester():
            gate.request_approval("pending.com", 443)

        t = threading.Thread(target=requester)
        t.start()
        time.sleep(0.2)

        pending = gate.get_pending()
        assert len(pending) == 1
        assert pending[0]["domain"] == "pending.com"
        assert "waiting_seconds" in pending[0]

        gate.deny("pending.com")
        t.join(timeout=5)

    def test_history_recorded(self, gate):
        def requester():
            gate.request_approval("hist.com", 443)

        t = threading.Thread(target=requester)
        t.start()
        time.sleep(0.2)
        gate.approve("hist.com")
        t.join(timeout=5)

        history = gate.get_history()
        assert len(history) == 1
        assert history[0]["decision"] == "approved"

    def test_duplicate_requests_share_pending(self, gate):
        """Multiple requests for the same domain share one PendingRequest."""
        results = [None, None]

        def requester(idx):
            results[idx] = gate.request_approval("shared.com", 443)

        t1 = threading.Thread(target=requester, args=(0,))
        t2 = threading.Thread(target=requester, args=(1,))
        t1.start()
        t2.start()
        time.sleep(0.3)

        assert len(gate.get_pending()) == 1
        gate.approve("shared.com")
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert results[0] is True
        assert results[1] is True

    def test_alerts_fired_on_pending(self, gate):
        def requester():
            gate.request_approval("alertdomain.com", 443)

        t = threading.Thread(target=requester)
        t.start()
        time.sleep(0.2)
        gate.deny("alertdomain.com")
        t.join(timeout=5)

        gate.alerts.fire.assert_called()
