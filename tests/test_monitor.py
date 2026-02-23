"""Tests for monitor.py."""

import threading
import time
from unittest.mock import MagicMock

import pytest

from crabpot.monitor import SecurityMonitor, SUSPICIOUS_PROCESSES


@pytest.fixture
def mock_dm():
    """Create a mock DockerManager."""
    dm = MagicMock()
    dm.get_status.return_value = "running"
    dm.stats_snapshot.return_value = {
        "cpu_percent": 10.0,
        "memory_usage": 256 * 1024 * 1024,
        "memory_limit": 2 * 1024 * 1024 * 1024,
        "memory_percent": 12.5,
        "network_rx": 1000,
        "network_tx": 500,
        "pids": 10,
        "timestamp": "",
    }
    dm.get_top.return_value = [{"CMD": "node app.js"}]
    dm.get_health.return_value = "healthy"
    dm.exec_run.return_value = (
        "State Recv-Q Send-Q Local Remote\n"
        "LISTEN 0 0 127.0.0.1:18789 0.0.0.0:*"
    )
    dm.get_logs.return_value = iter([])
    dm.events_stream.return_value = iter([])
    return dm


@pytest.fixture
def mock_alerts():
    """Create a mock AlertDispatcher."""
    return MagicMock()


@pytest.fixture
def monitor(mock_dm, mock_alerts):
    """Create a SecurityMonitor with mocks."""
    return SecurityMonitor(
        docker_manager=mock_dm,
        alert_dispatcher=mock_alerts,
        cpu_sustain_seconds=2,
    )


def _wait_for_alert(mock_alerts, severity, source, timeout=10):
    """Wait until a matching alert is fired, using polling instead of time.sleep."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for call in mock_alerts.fire.call_args_list:
            if call[0][0] == severity and call[0][1] == source:
                return True
        time.sleep(0.1)
    return False


class TestSecurityMonitor:
    def test_start_creates_threads(self, monitor):
        monitor.start()
        assert len(monitor._threads) == 6
        monitor.stop()

    def test_stop_sets_event(self, monitor):
        monitor.start()
        monitor.stop()
        assert monitor._stop_event.is_set()

    def test_pause_and_resume(self, monitor):
        monitor.pause_monitoring()
        assert monitor._is_paused()
        monitor.resume_monitoring()
        assert not monitor._is_paused()

    def test_suspicious_process_names(self):
        assert "sh" in SUSPICIOUS_PROCESSES
        assert "bash" in SUSPICIOUS_PROCESSES
        assert "python" in SUSPICIOUS_PROCESSES
        assert "nc" in SUSPICIOUS_PROCESSES
        assert "node" not in SUSPICIOUS_PROCESSES

    def test_cpu_warning_after_sustained(self, mock_dm, mock_alerts):
        """Test that CPU warnings fire after sustained high usage."""
        mock_dm.stats_snapshot.return_value = {
            "cpu_percent": 95.0,
            "memory_percent": 50.0,
            "memory_usage": 1024 * 1024 * 1024,
            "memory_limit": 2 * 1024 * 1024 * 1024,
            "network_rx": 0,
            "network_tx": 0,
            "pids": 10,
            "timestamp": "",
        }

        mon = SecurityMonitor(
            docker_manager=mock_dm,
            alert_dispatcher=mock_alerts,
            cpu_sustain_seconds=1,
        )
        mon.start()
        assert _wait_for_alert(mock_alerts, "WARNING", "stats"), \
            "CPU warning was not fired within timeout"
        mon.stop()

    def test_suspicious_process_triggers_critical(self, mock_dm, mock_alerts):
        """Test that suspicious process detection fires CRITICAL alert."""
        mock_dm.get_top.return_value = [
            {"CMD": "node app.js"},
            {"CMD": "/bin/bash"},
        ]

        mon = SecurityMonitor(
            docker_manager=mock_dm,
            alert_dispatcher=mock_alerts,
        )
        mon.start()
        assert _wait_for_alert(mock_alerts, "CRITICAL", "processes"), \
            "Process CRITICAL alert was not fired within timeout"
        mon.stop()

    def test_unhealthy_triggers_critical(self, mock_dm, mock_alerts):
        """Test that consecutive unhealthy checks fire CRITICAL."""
        mock_dm.get_health.return_value = "unhealthy"

        mon = SecurityMonitor(
            docker_manager=mock_dm,
            alert_dispatcher=mock_alerts,
        )
        mon._consecutive_unhealthy = 1
        mon.start()
        assert _wait_for_alert(mock_alerts, "CRITICAL", "health"), \
            "Health CRITICAL alert was not fired within timeout"
        mon.stop()

    def test_auto_pause_on_critical(self, mock_dm, mock_alerts):
        """Test that CRITICAL alerts trigger auto-pause."""
        mock_dm.get_top.return_value = [{"CMD": "/bin/sh"}]

        mon = SecurityMonitor(
            docker_manager=mock_dm,
            alert_dispatcher=mock_alerts,
        )
        mon.start()
        assert _wait_for_alert(mock_alerts, "CRITICAL", "processes"), \
            "Process CRITICAL alert was not fired within timeout"
        mon.stop()

        mock_dm.pause.assert_called()

    def test_memory_alert_has_cooldown(self, mock_dm, mock_alerts):
        """Test that memory alerts don't fire every 2 seconds."""
        mock_dm.stats_snapshot.return_value = {
            "cpu_percent": 10.0,
            "memory_percent": 90.0,
            "memory_usage": 1800 * 1024 * 1024,
            "memory_limit": 2 * 1024 * 1024 * 1024,
            "network_rx": 0,
            "network_tx": 0,
            "pids": 10,
            "timestamp": "",
        }

        mon = SecurityMonitor(
            docker_manager=mock_dm,
            alert_dispatcher=mock_alerts,
        )
        mon.start()
        assert _wait_for_alert(mock_alerts, "WARNING", "stats"), \
            "Memory warning was not fired"
        time.sleep(3)
        mon.stop()

        # Should have fired only once (cooldown is 60s, we waited 3s)
        memory_alerts = [
            c for c in mock_alerts.fire.call_args_list
            if c[0][0] == "WARNING" and c[0][1] == "stats" and "Memory" in c[0][2]
        ]
        assert len(memory_alerts) == 1

    def test_network_deduplicates_connections(self, mock_dm, mock_alerts):
        """Test that network watcher doesn't re-alert on the same connection."""
        mock_dm.exec_run.return_value = (
            "State Recv-Q Send-Q Local Remote\n"
            "ESTAB 0 0 172.17.0.2:18789 8.8.8.8:443"
        )

        mon = SecurityMonitor(
            docker_manager=mock_dm,
            alert_dispatcher=mock_alerts,
        )
        mon.start()
        assert _wait_for_alert(mock_alerts, "WARNING", "network"), \
            "Network warning was not fired"
        time.sleep(2)
        mon.stop()

        network_alerts = [
            c for c in mock_alerts.fire.call_args_list
            if c[0][0] == "WARNING" and c[0][1] == "network"
        ]
        assert len(network_alerts) == 1
