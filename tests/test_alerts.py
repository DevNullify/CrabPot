"""Tests for alerts.py."""

import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from crabpot.alerts import AlertDispatcher, _sanitize_for_toast


@pytest.fixture
def data_dir(tmp_path):
    """Provide a temporary data directory."""
    return tmp_path / "data"


@pytest.fixture
def dispatcher(data_dir):
    """Provide an AlertDispatcher with temp directory."""
    return AlertDispatcher(data_dir=data_dir)


class TestAlertDispatcher:
    def test_fire_writes_log(self, dispatcher, data_dir):
        dispatcher.fire("WARNING", "test", "Test alert message")

        log_file = data_dir / "alerts.log"
        assert log_file.exists()

        with open(log_file) as f:
            entry = json.loads(f.readline())

        assert entry["severity"] == "WARNING"
        assert entry["source"] == "test"
        assert entry["message"] == "Test alert message"
        assert "timestamp" in entry

    def test_fire_adds_to_history(self, dispatcher):
        dispatcher.fire("INFO", "test", "Message 1")
        dispatcher.fire("WARNING", "test", "Message 2")

        history = dispatcher.get_history()
        assert len(history) == 2
        assert history[0]["message"] == "Message 1"
        assert history[1]["message"] == "Message 2"

    def test_get_history_last(self, dispatcher):
        for i in range(10):
            dispatcher.fire("INFO", "test", f"Message {i}")

        history = dispatcher.get_history(last=3)
        assert len(history) == 3
        assert history[0]["message"] == "Message 7"

    def test_get_history_severity_filter(self, dispatcher):
        dispatcher.fire("INFO", "test", "Info message")
        dispatcher.fire("WARNING", "test", "Warning message")
        dispatcher.fire("CRITICAL", "test", "Critical message")

        warnings = dispatcher.get_history(severity="WARNING")
        assert len(warnings) == 1
        assert warnings[0]["message"] == "Warning message"

    def test_get_alert_counts(self, dispatcher):
        dispatcher.fire("INFO", "test", "Info 1")
        dispatcher.fire("INFO", "test", "Info 2")
        dispatcher.fire("WARNING", "test", "Warning 1")
        dispatcher.fire("CRITICAL", "test", "Critical 1")

        counts = dispatcher.get_alert_counts()
        assert counts["INFO"] == 2
        assert counts["WARNING"] == 1
        assert counts["CRITICAL"] == 1

    def test_history_bounded(self, dispatcher):
        for i in range(1100):
            dispatcher.fire("INFO", "test", f"Message {i}")

        # Should have been trimmed to 500
        history = dispatcher.get_history(last=10000)
        assert len(history) <= 600  # 500 from trim + up to 100 new before next trim

    def test_websocket_emit(self, dispatcher):
        mock_sio = MagicMock()
        dispatcher.set_socketio(mock_sio)

        dispatcher.fire("WARNING", "test", "Alert via WS")

        mock_sio.emit.assert_called()
        # Find the alert emit (not stats)
        alert_calls = [c for c in mock_sio.emit.call_args_list if c[0][0] == "alert"]
        assert len(alert_calls) == 1

    def test_push_stats(self, dispatcher):
        mock_sio = MagicMock()
        dispatcher.set_socketio(mock_sio)

        stats = {"cpu_percent": 42.0}
        dispatcher.push_stats(stats)

        mock_sio.emit.assert_called_once_with("stats", stats, namespace="/")

    def test_load_history_from_file(self, data_dir):
        data_dir.mkdir(parents=True, exist_ok=True)
        log_file = data_dir / "alerts.log"

        entries = [
            {
                "severity": "INFO",
                "source": "test",
                "message": "Old alert 1",
                "timestamp": "12:00:00",
            },
            {
                "severity": "WARNING",
                "source": "test",
                "message": "Old alert 2",
                "timestamp": "12:01:00",
            },
        ]
        with open(log_file, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        dispatcher = AlertDispatcher(data_dir=data_dir)
        history = dispatcher.get_history()
        assert len(history) == 2
        assert history[0]["message"] == "Old alert 1"

    @patch("crabpot.alerts.subprocess.Popen")
    def test_toast_on_critical(self, mock_popen, dispatcher):
        dispatcher.fire("CRITICAL", "test", "Critical alert!")

        mock_popen.assert_called_once()
        args = mock_popen.call_args
        assert args[0][0][0] == "powershell.exe"

    @patch("crabpot.alerts.subprocess.Popen", side_effect=FileNotFoundError)
    def test_toast_skipped_on_non_wsl(self, mock_popen, dispatcher):
        # Should not raise even when powershell.exe is not found
        dispatcher.fire("CRITICAL", "test", "Critical without toast")

    def test_thread_safety(self, dispatcher):
        """Test that concurrent fires don't corrupt state."""
        errors = []

        def fire_many(severity, count):
            try:
                for i in range(count):
                    dispatcher.fire(severity, "test", f"{severity} {i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=fire_many, args=("INFO", 50)),
            threading.Thread(target=fire_many, args=("WARNING", 50)),
            threading.Thread(target=fire_many, args=("CRITICAL", 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        counts = dispatcher.get_alert_counts()
        assert counts["INFO"] == 50
        assert counts["WARNING"] == 50
        assert counts["CRITICAL"] == 50


class TestSanitizeForToast:
    def test_strips_dangerous_characters(self):
        result = _sanitize_for_toast("$('evil');rm -rf /")
        assert "$" not in result
        assert "'" not in result
        assert ";" not in result

    def test_preserves_safe_characters(self):
        assert _sanitize_for_toast("Hello, world!") == "Hello, world!"

    def test_strips_backticks(self):
        assert "`" not in _sanitize_for_toast("test`command`")

    def test_strips_pipe(self):
        assert "|" not in _sanitize_for_toast("test|command")

    def test_truncates_long_input(self):
        long_input = "a" * 500
        assert len(_sanitize_for_toast(long_input)) == 200

    def test_no_sanitization_needed(self):
        assert _sanitize_for_toast("simple text 123") == "simple text 123"

    def test_preserves_basic_punctuation(self):
        result = _sanitize_for_toast("CPU at 95.3% (2048MB)")
        assert "95.3" in result
        assert "2048MB" in result
