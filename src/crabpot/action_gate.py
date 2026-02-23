"""Human-in-the-loop approval system for network egress requests.

When the egress proxy encounters an unknown domain, the ActionGate queues it
for human review. The pending request blocks the proxy thread until the human
approves, denies, or the request times out.

Approvals can be:
  - Session: valid until crabpot stop (stored in EgressPolicy.session_approved)
  - Permanent: written to the allowlist file
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60  # seconds to wait for human decision


@dataclass
class PendingRequest:
    """A network egress request awaiting human approval."""

    domain: str
    port: int
    timestamp: float = field(default_factory=time.time)
    approved: Optional[bool] = None
    event: threading.Event = field(default_factory=threading.Event)

    def wait(self, timeout: float = DEFAULT_TIMEOUT) -> bool:
        """Block until a decision is made or timeout expires.

        Returns True if approved, False if denied or timed out.
        """
        self.event.wait(timeout=timeout)
        return self.approved is True

    def approve(self) -> None:
        self.approved = True
        self.event.set()

    def deny(self) -> None:
        self.approved = False
        self.event.set()


class ActionGate:
    """Manages pending approval requests and routes decisions.

    Integrates with:
      - EgressProxy: blocks on request_approval() until a decision
      - AlertDispatcher: fires alerts for pending/approved/denied requests
      - DashboardServer: pushes WebSocket events for the approval UI
      - CLI (crabpot approve): reads pending list, sends decisions
    """

    def __init__(self, egress_policy, alert_dispatcher=None, timeout: float = DEFAULT_TIMEOUT):
        self.policy = egress_policy
        self.alerts = alert_dispatcher
        self.timeout = timeout
        self._lock = threading.Lock()
        self._pending: dict[str, PendingRequest] = {}
        self._history: list[dict] = []

    def request_approval(self, domain: str, port: int = 443) -> bool:
        """Request human approval for a domain. Blocks until decision or timeout.

        If the same domain is already pending, reuses the existing request
        (multiple proxy threads for the same domain share one approval).

        Returns True if approved, False if denied or timed out.
        """
        domain = domain.lower()

        with self._lock:
            if domain in self._pending:
                req = self._pending[domain]
            else:
                req = PendingRequest(domain=domain, port=port)
                self._pending[domain] = req
                self._notify_pending(req)

        approved = req.wait(timeout=self.timeout)

        with self._lock:
            self._pending.pop(domain, None)
            self._history.append({
                "domain": domain,
                "port": port,
                "decision": "approved" if approved else "denied",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })

        if approved:
            self._log_decision(domain, "APPROVED")
        else:
            self._log_decision(domain, "DENIED (timeout or explicit)")

        return approved

    def approve(self, domain: str, permanent: bool = False) -> bool:
        """Approve a pending domain request.

        Args:
            domain: The domain to approve.
            permanent: If True, add to the permanent allowlist.

        Returns True if there was a pending request, False otherwise.
        """
        domain = domain.lower()

        if permanent:
            self.policy.add_permanent(domain)
        else:
            self.policy.session_approve(domain)

        with self._lock:
            req = self._pending.get(domain)
            if req:
                req.approve()
                return True
        return False

    def deny(self, domain: str) -> bool:
        """Deny a pending domain request."""
        domain = domain.lower()
        self.policy.session_deny(domain)

        with self._lock:
            req = self._pending.get(domain)
            if req:
                req.deny()
                return True
        return False

    def get_pending(self) -> list[dict]:
        """Get a snapshot of all pending approval requests."""
        with self._lock:
            return [
                {
                    "domain": req.domain,
                    "port": req.port,
                    "timestamp": time.strftime(
                        "%H:%M:%S", time.localtime(req.timestamp)
                    ),
                    "waiting_seconds": int(time.time() - req.timestamp),
                }
                for req in self._pending.values()
            ]

    def get_history(self, last: int = 50) -> list[dict]:
        """Get recent approval history."""
        with self._lock:
            return list(self._history[-last:])

    def _notify_pending(self, req: PendingRequest) -> None:
        """Fire an alert and push a WebSocket event for a new pending request."""
        if self.alerts:
            self.alerts.fire(
                "WARNING",
                "egress",
                f"Approval needed: {req.domain}:{req.port} — "
                f"approve with 'crabpot approve {req.domain}' or via dashboard",
            )

    def _log_decision(self, domain: str, decision: str) -> None:
        """Log the approval decision."""
        if self.alerts:
            severity = "INFO" if "APPROVED" in decision else "WARNING"
            self.alerts.fire(severity, "egress", f"Egress {decision}: {domain}")
