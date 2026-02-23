"""Tests for utils.py shared utilities."""

from crabpot.utils import format_uptime


class TestFormatUptime:
    def test_none_returns_dash(self):
        assert format_uptime(None) == "--"

    def test_empty_string_returns_dash(self):
        assert format_uptime("") == "--"

    def test_invalid_format_returns_dash(self):
        assert format_uptime("not-a-date") == "--"

    def test_future_date_returns_dash(self):
        assert format_uptime("2099-01-01T00:00:00Z") == "--"

    def test_recent_date_returns_seconds(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        result = format_uptime(now)
        # Should be a few seconds
        assert "s" in result

    def test_z_suffix_handled(self):
        result = format_uptime("2020-01-01T00:00:00Z")
        assert "h" in result  # Should show hours since 2020
