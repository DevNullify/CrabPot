"""Multi-channel alert dispatcher: toast + terminal + log + WebSocket."""

import base64
import contextlib
import json
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


class AlertDispatcher:
    """Routes alerts to Windows toast, terminal, log file, and WebSocket."""

    def __init__(self, data_dir: Optional[Path] = None, socketio=None):
        self.data_dir = data_dir or (Path.home() / ".crabpot" / "data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.data_dir / "alerts.log"
        self.socketio = socketio
        self._lock = threading.Lock()
        self._history: list[dict] = []
        self._load_history()

    def set_socketio(self, sio):
        """Set the SocketIO instance for WebSocket alerts."""
        self.socketio = sio

    def fire(self, severity: str, source: str, message: str) -> None:
        """Dispatch an alert through all channels."""
        alert = {
            "severity": severity,
            "source": source,
            "message": message,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "timestamp_full": datetime.now().isoformat(),
        }

        with self._lock:
            self._history.append(alert)
            # Keep history bounded
            if len(self._history) > 1000:
                self._history = self._history[-500:]

        self._write_log(alert)
        self._print_terminal(alert)
        self._send_websocket(alert)

        if severity == "CRITICAL":
            self._send_toast(f"CrabPot CRITICAL: {source}", message)

    def push_stats(self, stats: dict) -> None:
        """Push stats to the WebSocket dashboard."""
        if self.socketio:
            with contextlib.suppress(Exception):
                self.socketio.emit("stats", stats, namespace="/")

    def get_history(self, last: int = 20, severity: Optional[str] = None) -> list:
        """Get recent alert history, optionally filtered by severity."""
        with self._lock:
            history = list(self._history)

        if severity:
            history = [a for a in history if a.get("severity") == severity]

        return history[-last:]

    def get_alert_counts(self) -> dict:
        """Get counts by severity."""
        with self._lock:
            counts = {"CRITICAL": 0, "WARNING": 0, "INFO": 0}
            for alert in self._history:
                sev = alert.get("severity", "INFO")
                if sev in counts:
                    counts[sev] += 1
            return counts

    def _print_terminal(self, alert: dict) -> None:
        """Print a colored alert to the terminal."""
        from rich.console import Console

        console = Console(stderr=True)
        sev = alert["severity"]
        colors = {"CRITICAL": "bold red", "WARNING": "yellow", "INFO": "blue"}
        style = colors.get(sev, "white")

        console.print(
            f"[{style}][{sev}][/{style}] "
            f"[dim]{alert['timestamp']}[/dim] "
            f"[{style}]{alert['source']}[/{style}]: {alert['message']}"
        )

    def _write_log(self, alert: dict) -> None:
        """Append the alert to the log file as JSON."""
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(alert) + "\n")
        except OSError:
            pass

    def _send_websocket(self, alert: dict) -> None:
        """Push the alert to the WebSocket dashboard."""
        if self.socketio:
            with contextlib.suppress(Exception):
                self.socketio.emit("alert", alert, namespace="/")

    def _send_toast(self, title: str, message: str) -> None:
        """Send a Windows toast notification via powershell.exe from WSL2.

        Uses -EncodedCommand with strict input sanitization to prevent
        PowerShell injection from attacker-controlled log content.
        """
        try:
            safe_title = _sanitize_for_toast(title)
            safe_message = _sanitize_for_toast(message)
            ps_script = (
                "[Windows.UI.Notifications.ToastNotificationManager, "
                "Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
                "$template = [Windows.UI.Notifications.ToastNotificationManager]::"
                "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::"
                "ToastText02); "
                "$text = $template.GetElementsByTagName('text'); "
                f"$text[0].AppendChild($template.CreateTextNode('{safe_title}')) > $null; "
                f"$text[1].AppendChild($template.CreateTextNode('{safe_message}')) > $null; "
                "$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
                "[Windows.UI.Notifications.ToastNotificationManager]::"
                "CreateToastNotifier('CrabPot').Show($toast)"
            )
            encoded = base64.b64encode(ps_script.encode("utf-16-le")).decode("ascii")
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-EncodedCommand", encoded],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass  # Not on WSL2, skip toast

    def _load_history(self) -> None:
        """Load existing alert history from the log file."""
        if not self.log_file.exists():
            return
        try:
            with open(self.log_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        with contextlib.suppress(json.JSONDecodeError):
                            self._history.append(json.loads(line))
            # Keep bounded
            if len(self._history) > 1000:
                self._history = self._history[-500:]
        except OSError:
            pass


def _sanitize_for_toast(s: str) -> str:
    """Sanitize a string for safe use in PowerShell toast notifications.

    Uses an allowlist approach: only alphanumeric chars, spaces, and basic
    punctuation are kept. Everything else is stripped. This prevents
    injection via $(), ;, |, `, and other PowerShell metacharacters.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9 .,!?:/()\-]", "", s)
    return sanitized[:200]
