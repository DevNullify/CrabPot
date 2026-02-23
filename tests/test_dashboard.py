"""Tests for dashboard.py Flask routes."""

import json
from unittest.mock import MagicMock

import pytest

from crabpot.dashboard import DashboardServer


@pytest.fixture
def mock_dm():
    dm = MagicMock()
    dm.get_status.return_value = "running"
    dm.get_health.return_value = "healthy"
    dm.get_start_time.return_value = None
    dm.get_logs.return_value = iter([])
    return dm


@pytest.fixture
def mock_alerts():
    alerts = MagicMock()
    alerts.get_alert_counts.return_value = {"CRITICAL": 0, "WARNING": 1, "INFO": 3}
    alerts.get_history.return_value = []
    return alerts


@pytest.fixture
def mock_monitor():
    monitor = MagicMock()
    monitor.get_latest_stats.return_value = {
        "cpu_percent": 15.0,
        "memory_usage": 512 * 1024 * 1024,
        "memory_limit": 2 * 1024 * 1024 * 1024,
        "memory_percent": 25.0,
        "network_rx": 100000,
        "network_tx": 50000,
        "pids": 20,
    }
    return monitor


@pytest.fixture
def dashboard(mock_dm, mock_alerts, mock_monitor):
    return DashboardServer(
        docker_manager=mock_dm,
        alert_dispatcher=mock_alerts,
        security_monitor=mock_monitor,
    )


@pytest.fixture
def client(dashboard):
    dashboard.app.config["TESTING"] = True
    return dashboard.app.test_client()


class TestDashboardRoutes:
    def test_index_returns_html(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert b"CRABPOT" in response.data

    def test_api_status_returns_json(self, client):
        response = client.get("/api/status")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "running"
        assert data["health"] == "healthy"
        assert data["alert_counts"]["WARNING"] == 1
        assert data["stats"]["cpu_percent"] == 15.0


class TestDashboardSecurity:
    def test_secret_key_is_random(self, dashboard):
        assert dashboard.app.config["SECRET_KEY"] != "crabpot-local-dashboard"
        assert len(dashboard.app.config["SECRET_KEY"]) == 64  # hex(32) = 64 chars
