"""Flask + SocketIO web dashboard for CrabPot."""

import logging
import secrets
import threading
import time

from flask import Flask, jsonify
from flask_socketio import SocketIO

from crabpot.dashboard_html import DASHBOARD_HTML
from crabpot.utils import format_uptime


# Suppress Flask/Werkzeug request logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)


class DashboardServer:
    """Web dashboard serving at http://localhost:9876 with real-time WebSocket updates."""

    def __init__(
        self, docker_manager=None, alert_dispatcher=None, security_monitor=None,
        action_gate=None, egress_policy=None, port=9876, runtime=None,
        target="docker", security_preset="standard",
    ):
        # Accept either runtime or docker_manager for backward compatibility
        self.dm = runtime or docker_manager
        self.alerts = alert_dispatcher
        self.monitor = security_monitor
        self.gate = action_gate
        self.egress_policy = egress_policy
        self.port = port
        self.target = target
        self.security_preset = security_preset

        self.app = Flask(__name__)
        self.app.config["SECRET_KEY"] = secrets.token_hex(32)

        allowed_origins = [
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        ]
        self.socketio = SocketIO(
            self.app, cors_allowed_origins=allowed_origins, async_mode="threading"
        )

        # Wire up the alert dispatcher to emit via WebSocket
        self.alerts.set_socketio(self.socketio)

        self._setup_routes()
        self._setup_socketio()
        self._stop_event = threading.Event()

    def run(self) -> None:
        """Start the dashboard server (blocking)."""
        # Start background status pusher
        self._start_status_pusher()
        self._start_log_streamer()

        self.socketio.run(
            self.app,
            host="127.0.0.1",
            port=self.port,
            debug=False,
            use_reloader=False,
            log_output=False,
        )

    def stop(self) -> None:
        """Signal the dashboard to stop."""
        self._stop_event.set()

    def _setup_routes(self) -> None:
        """Register Flask HTTP routes."""

        @self.app.route("/")
        def index():
            return DASHBOARD_HTML

        @self.app.route("/api/status")
        def api_status():
            status = self.dm.get_status()
            health = self.dm.get_health()
            stats = self.monitor.get_latest_stats()
            alert_counts = self.alerts.get_alert_counts()

            result = {
                "status": status,
                "health": health,
                "stats": stats,
                "alert_counts": alert_counts,
                "uptime": self._get_uptime(),
                "target": self.target,
                "security_preset": self.security_preset,
            }

            if self.gate:
                result["pending_approvals"] = self.gate.get_pending()

            if self.egress_policy:
                result["egress_allowlist_count"] = len(self.egress_policy.get_allowlist())

            return jsonify(result)

        @self.app.route("/api/egress/pending")
        def api_egress_pending():
            if not self.gate:
                return jsonify([])
            return jsonify(self.gate.get_pending())

        @self.app.route("/api/egress/audit")
        def api_egress_audit():
            if not self.egress_policy:
                return jsonify([])
            return jsonify(self.egress_policy.get_audit_log(last=100))

        @self.app.route("/api/egress/allowlist")
        def api_egress_allowlist():
            if not self.egress_policy:
                return jsonify([])
            return jsonify(self.egress_policy.get_allowlist())

    def _setup_socketio(self) -> None:
        """Register WebSocket event handlers."""

        @self.socketio.on("connect")
        def handle_connect():
            # Send initial state on connect
            self.socketio.emit("status", {
                "status": self.dm.get_status(),
                "health": self.dm.get_health(),
                "uptime": self._get_uptime(),
            })

            # Send recent alerts
            for alert in self.alerts.get_history(last=20):
                self.socketio.emit("alert", alert)

        @self.socketio.on("command")
        def handle_command(data):
            action = data.get("action", "")
            valid_actions = {"start", "stop", "pause", "resume", "destroy"}
            if action not in valid_actions:
                return
            try:
                if action == "start":
                    self.dm.start()
                elif action == "stop":
                    self.dm.stop()
                elif action == "pause":
                    self.dm.pause()
                    self.monitor.pause_monitoring()
                elif action == "resume":
                    self.dm.resume()
                    self.monitor.resume_monitoring()
                elif action == "destroy":
                    self.monitor.stop()
                    self.dm.destroy()

                self.socketio.emit("status", {
                    "status": self.dm.get_status(),
                    "health": self.dm.get_health(),
                    "uptime": self._get_uptime(),
                })
            except Exception as e:
                self.socketio.emit("error", {
                    "message": f"Command '{action}' failed: {e}",
                })

        @self.socketio.on("egress_approve")
        def handle_egress_approve(data):
            domain = data.get("domain", "")
            permanent = data.get("permanent", False)
            if not domain or not self.gate:
                return
            self.gate.approve(domain, permanent=permanent)
            self.socketio.emit("egress_update", {
                "domain": domain,
                "action": "approved",
                "permanent": permanent,
            })

        @self.socketio.on("egress_deny")
        def handle_egress_deny(data):
            domain = data.get("domain", "")
            if not domain or not self.gate:
                return
            self.gate.deny(domain)
            self.socketio.emit("egress_update", {
                "domain": domain,
                "action": "denied",
            })

    def _start_status_pusher(self) -> None:
        """Background thread that pushes container status every 5 seconds."""
        def pusher():
            while not self._stop_event.is_set():
                try:
                    self.socketio.emit("status", {
                        "status": self.dm.get_status(),
                        "health": self.dm.get_health(),
                        "uptime": self._get_uptime(),
                    })
                except Exception:
                    pass
                self._stop_event.wait(timeout=5)

        t = threading.Thread(target=pusher, name="dashboard-status", daemon=True)
        t.start()

    def _start_log_streamer(self) -> None:
        """Background thread that streams container logs to WebSocket clients."""
        def streamer():
            while not self._stop_event.is_set():
                try:
                    if self.dm.get_status() == "running":
                        for line in self.dm.get_logs(follow=True, tail=0):
                            if self._stop_event.is_set():
                                return
                            self.socketio.emit("log", {"line": line})
                except Exception:
                    pass
                self._stop_event.wait(timeout=5)

        t = threading.Thread(target=streamer, name="dashboard-logs", daemon=True)
        t.start()

    def _get_uptime(self) -> str:
        """Calculate container uptime as a human-readable string."""
        return format_uptime(self.dm.get_start_time())
