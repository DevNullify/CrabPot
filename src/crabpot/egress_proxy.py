"""Lightweight HTTP/HTTPS egress proxy with policy enforcement.

Runs on the host and gates all container traffic. The container is
configured with HTTP_PROXY/HTTPS_PROXY pointing to this proxy.

For HTTPS: handles CONNECT tunneling (can see domain, not payload).
For HTTP: forwards requests (can inspect URL and body for secrets).
"""

import http.server
import logging
import select
import socket
import socketserver
import threading
import urllib.request
from typing import Optional

from crabpot.action_gate import ActionGate
from crabpot.egress_policy import Decision, EgressPolicy

logger = logging.getLogger(__name__)

TUNNEL_TIMEOUT = 60
BUFFER_SIZE = 65536


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    """HTTP proxy request handler with egress policy enforcement.

    Class-level attributes are set by EgressProxy before the server starts.
    """

    policy: EgressPolicy
    gate: Optional[ActionGate]

    # Suppress per-request log lines from BaseHTTPRequestHandler
    def log_message(self, format, *args):
        logger.debug("proxy: %s", format % args)

    def do_CONNECT(self):
        """Handle HTTPS CONNECT tunneling — enforce domain allowlist."""
        try:
            host, port_str = self.path.rsplit(":", 1)
            port = int(port_str)
        except ValueError:
            self.send_error(400, "Bad CONNECT target")
            return

        decision = self._enforce(host, port, "CONNECT")
        if decision != Decision.ALLOW:
            self.send_error(403, f"Blocked by CrabPot egress policy: {host}")
            return

        # Establish upstream connection
        try:
            remote = socket.create_connection((host, port), timeout=10)
        except OSError as e:
            self.send_error(502, f"Cannot reach {host}:{port}")
            logger.debug("CONNECT upstream failed for %s:%d: %s", host, port, e)
            return

        self.send_response(200, "Connection Established")
        self.end_headers()

        # Bidirectional tunnel
        self._tunnel(self.connection, remote)

    def do_GET(self):
        self._handle_http()

    def do_POST(self):
        self._handle_http()

    def do_PUT(self):
        self._handle_http()

    def do_DELETE(self):
        self._handle_http()

    def do_PATCH(self):
        self._handle_http()

    def do_HEAD(self):
        self._handle_http()

    def do_OPTIONS(self):
        self._handle_http()

    def _handle_http(self):
        """Handle plain HTTP requests — can inspect URL and body."""
        # Parse target URL
        url = self.path
        if not url.startswith("http"):
            self.send_error(400, "Absolute URL required for proxy requests")
            return

        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            host = parsed.hostname or ""
            port = parsed.port or 80
        except Exception:
            self.send_error(400, "Cannot parse URL")
            return

        decision = self._enforce(host, port, self.command)
        if decision != Decision.ALLOW:
            self.send_error(403, f"Blocked by CrabPot egress policy: {host}")
            return

        # Read request body (for secret scanning on HTTP)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        # Scan for secrets in the URL and body
        scan_content = url + " " + body.decode("utf-8", errors="replace")
        secrets_found = self.policy.scan_for_secrets(scan_content)
        if secrets_found:
            self.policy.log_attempt(host, port, self.command, "blocked_secrets")
            logger.warning("Secret pattern detected in HTTP request to %s", host)
            if self.gate and self.gate.alerts:
                self.gate.alerts.fire(
                    "CRITICAL",
                    "egress",
                    f"Blocked: secret pattern detected in request to {host}",
                )
            self.send_error(403, "Request blocked: potential secret exfiltration detected")
            return

        # Forward the request
        try:
            req = urllib.request.Request(
                url,
                data=body if body else None,
                method=self.command,
            )
            # Copy headers (except proxy-specific ones)
            for key, value in self.headers.items():
                if key.lower() not in ("proxy-connection", "proxy-authorization", "host"):
                    req.add_header(key, value)

            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for key, value in resp.getheaders():
                    if key.lower() not in ("transfer-encoding",):
                        self.send_header(key, value)
                self.end_headers()
                while True:
                    chunk = resp.read(BUFFER_SIZE)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except urllib.error.HTTPError as e:
            self.send_error(e.code, str(e.reason))
        except Exception as e:
            self.send_error(502, f"Upstream error: {e}")

    def _enforce(self, host: str, port: int, method: str) -> Decision:
        """Check domain against policy, request approval if needed."""
        decision = self.policy.check_domain(host)
        self.policy.log_attempt(host, port, method, decision.value)

        if decision == Decision.PENDING and self.gate:
            approved = self.gate.request_approval(host, port)
            final = Decision.ALLOW if approved else Decision.DENY
            self.policy.log_attempt(host, port, method, f"{final.value}_after_review")
            return final

        return decision

    def _tunnel(self, client_sock: socket.socket, remote_sock: socket.socket) -> None:
        """Bidirectional byte tunneling for CONNECT proxy."""
        sockets = [client_sock, remote_sock]
        try:
            while True:
                readable, _, errored = select.select(sockets, [], sockets, TUNNEL_TIMEOUT)
                if errored:
                    break
                if not readable:
                    break  # Timeout
                for sock in readable:
                    data = sock.recv(BUFFER_SIZE)
                    if not data:
                        return
                    target = remote_sock if sock is client_sock else client_sock
                    target.sendall(data)
        except (OSError, BrokenPipeError):
            pass
        finally:
            remote_sock.close()


class _ThreadingProxy(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Threaded HTTP proxy server."""

    daemon_threads = True
    allow_reuse_address = True


class EgressProxy:
    """Manages the egress proxy server lifecycle.

    Start with start() to run in a background thread.
    Stop with stop() for graceful shutdown.
    """

    def __init__(
        self,
        policy: EgressPolicy,
        gate: Optional[ActionGate] = None,
        host: str = "127.0.0.1",
        port: int = 9877,
    ):
        self.policy = policy
        self.gate = gate
        self.host = host
        self.port = port
        self._server: Optional[_ThreadingProxy] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the proxy server in a background thread."""
        # Wire policy and gate into the handler class
        _ProxyHandler.policy = self.policy
        _ProxyHandler.gate = self.gate

        self._server = _ThreadingProxy((self.host, self.port), _ProxyHandler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="egress-proxy",
            daemon=True,
        )
        self._thread.start()
        logger.info("Egress proxy listening on %s:%d", self.host, self.port)

    def stop(self) -> None:
        """Shut down the proxy server."""
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
