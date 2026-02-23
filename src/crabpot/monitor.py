"""SecurityMonitor — conditional real-time security monitoring daemon."""

import logging
import re
import threading
import time
from typing import Optional

from docker.errors import APIError, NotFound

from crabpot.alerts import AlertDispatcher
from crabpot.security_presets import SecurityProfile

logger = logging.getLogger(__name__)

# Suspicious process names that should never run inside the sandbox
SUSPICIOUS_PROCESSES = {
    "sh",
    "bash",
    "dash",
    "zsh",
    "fish",
    "csh",
    "tcsh",
    "python",
    "python3",
    "perl",
    "ruby",
    "php",
    "lua",
    "nc",
    "ncat",
    "nmap",
    "socat",
    "telnet",
    "gcc",
    "cc",
    "make",
    "ld",
}

# Log patterns that indicate problems (ordered by severity)
LOG_PATTERNS = [
    # ── Prompt injection / exfiltration attempts ──
    (
        r"(?i)\b(curl|wget|fetch|http\.get|axios|request)\b.*(?:\bhttp[s]?://)",
        "CRITICAL",
        "Outbound HTTP call attempted",
    ),
    (
        r"(?i)\b(eval|exec|system|popen|subprocess|child_process\.exec)\b",
        "CRITICAL",
        "Dynamic code execution detected",
    ),
    (
        r"(?i)\b(apt|apt-get|pip|npm|yarn)\b\s+install\b",
        "CRITICAL",
        "Package installation attempted",
    ),
    (r"(?i)\b(chmod|chown|chgrp)\b.*\b\+[rwxs]\b", "WARNING", "Permission change attempted"),
    (
        r"(?i)\b(base64|xxd|openssl)\b.*\b(decode|enc|enc)\b",
        "WARNING",
        "Encoding/decoding tool usage",
    ),
    (
        r"(?i)\b(env|printenv|set)\b.*\b(KEY|SECRET|TOKEN|PASSWORD)\b",
        "CRITICAL",
        "Environment variable enumeration",
    ),
    (r"(?i)/etc/(passwd|shadow|hosts|resolv)", "CRITICAL", "Sensitive file access attempted"),
    (
        r"(?i)\b(whoami|hostname|ifconfig|ip\s+addr|uname)\b",
        "WARNING",
        "System reconnaissance detected",
    ),
    # ── General error patterns ──
    (r"(?i)\b(ERROR|FATAL|CRITICAL)\b", "WARNING", "Error detected in logs"),
    (r"(?i)\b(panic|segfault|core dump)\b", "WARNING", "Crash pattern in logs"),
    (r"(?i)\b(injection|unauthorized|forbidden)\b", "WARNING", "Security pattern in logs"),
    (r"(?i)\b(exec|spawn|child_process)\b.*\b(sh|bash|cmd)\b", "WARNING", "Shell spawn in logs"),
]

# Docker events that trigger alerts
CRITICAL_EVENTS = {"die", "oom", "kill"}
WARNING_EVENTS = {"restart"}

# Cooldown period (seconds) before re-alerting on the same condition
MEMORY_ALERT_COOLDOWN = 60


class SecurityMonitor:
    """Conditional real-time security monitoring daemon.

    Channels are spawned based on the SecurityProfile:
        - stats: Always on if resource_limits is True
        - processes: Only if process_watchdog is True
        - network: Only if network_auditor is True
        - logs: Only if log_scanner is True
        - health + events: Always on if any watcher is active
    """

    def __init__(
        self,
        docker_manager,
        alert_dispatcher: AlertDispatcher,
        security_profile: Optional[SecurityProfile] = None,
        cpu_threshold: float = 80.0,
        memory_threshold: float = 85.0,
        cpu_sustain_seconds: int = 30,
    ):
        self.dm = docker_manager
        self.alerts = alert_dispatcher
        self.profile = security_profile or SecurityProfile()
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.cpu_sustain_seconds = cpu_sustain_seconds

        self._stop_event = threading.Event()
        self._paused = threading.Event()
        self._threads: list = []

        # Shared state for stats
        self._latest_stats: Optional[dict] = None
        self._stats_lock = threading.Lock()

        # CPU spike tracking
        self._cpu_high_since: Optional[float] = None

        # Memory alert cooldown
        self._last_memory_alert: float = 0.0

        # Health tracking
        self._consecutive_unhealthy = 0

    def start(self) -> None:
        """Spawn watcher threads based on the security profile."""
        self._stop_event.clear()
        self._paused.clear()

        watchers = []

        if self.profile.resource_limits:
            watchers.append(("stats", self._watch_stats))
        if self.profile.process_watchdog:
            watchers.append(("processes", self._watch_processes))
        if self.profile.network_auditor:
            watchers.append(("network", self._watch_network))
        if self.profile.log_scanner:
            watchers.append(("logs", self._watch_logs))

        # Health and events always run if any monitoring is active
        if watchers:
            watchers.append(("health", self._watch_health))
            watchers.append(("events", self._watch_events))

        for name, target in watchers:
            t = threading.Thread(target=target, name=f"monitor-{name}", daemon=True)
            t.start()
            self._threads.append(t)

        channel_count = len(self._threads)
        if channel_count > 0:
            self.alerts.fire(
                "INFO", "monitor", f"Security monitor started ({channel_count} channels)"
            )

    def stop(self) -> None:
        """Signal all watcher threads to stop."""
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=3)
        self._threads.clear()

    def pause_monitoring(self) -> None:
        """Pause all polling-based watchers (streaming watchers continue)."""
        self._paused.set()

    def resume_monitoring(self) -> None:
        """Resume all watchers."""
        self._paused.clear()

    def get_latest_stats(self) -> Optional[dict]:
        """Get the most recently collected stats snapshot."""
        with self._stats_lock:
            return self._latest_stats

    def _should_stop(self) -> bool:
        return self._stop_event.is_set()

    def _is_paused(self) -> bool:
        return self._paused.is_set()

    def _sleep_interruptible(self, seconds: float) -> bool:
        """Sleep for `seconds`, returning True if interrupted by stop."""
        return self._stop_event.wait(timeout=seconds)

    def _auto_pause(self, reason: str) -> None:
        """Auto-freeze the container on CRITICAL alert (if enabled)."""
        if not self.profile.auto_pause_on_critical:
            return
        try:
            self.dm.pause()
            self.alerts.fire(
                "CRITICAL",
                "auto-pause",
                f"Container auto-frozen: {reason}. Resume with 'crabpot resume'.",
            )
        except Exception as e:
            self.alerts.fire("WARNING", "auto-pause", f"Failed to auto-pause: {e}")

    # ── 1. Stats watcher (CPU/memory) ────────────────────────────────

    def _watch_stats(self) -> None:
        """Monitor CPU and memory usage via Docker stats API."""
        while not self._should_stop():
            if self._is_paused():
                if self._sleep_interruptible(2):
                    return
                continue

            try:
                stats = self.dm.stats_snapshot()
                if stats is None:
                    if self._sleep_interruptible(5):
                        return
                    continue

                with self._stats_lock:
                    self._latest_stats = stats

                self.alerts.push_stats(stats)

                # CPU threshold check (sustained)
                if stats["cpu_percent"] > self.cpu_threshold:
                    now = time.time()
                    if self._cpu_high_since is None:
                        self._cpu_high_since = now
                    elif (now - self._cpu_high_since) >= self.cpu_sustain_seconds:
                        self.alerts.fire(
                            "WARNING",
                            "stats",
                            f"CPU at {stats['cpu_percent']}% for {self.cpu_sustain_seconds}s",
                        )
                        self._cpu_high_since = now
                else:
                    self._cpu_high_since = None

                # Memory threshold check (with cooldown)
                if stats["memory_percent"] > self.memory_threshold:
                    now = time.time()
                    if (now - self._last_memory_alert) >= MEMORY_ALERT_COOLDOWN:
                        self.alerts.fire(
                            "WARNING",
                            "stats",
                            f"Memory at {stats['memory_percent']}% "
                            f"({stats['memory_usage'] // (1024 * 1024)}MB)",
                        )
                        self._last_memory_alert = now

            except (NotFound, APIError) as e:
                logger.debug("Stats watcher Docker error (container may be stopped): %s", e)
            except Exception as e:
                self.alerts.fire("WARNING", "monitor", f"Stats watcher error: {e}")
                logger.exception("Unexpected error in stats watcher")

            if self._sleep_interruptible(2):
                return

    # ── 2. Process watchdog ──────────────────────────────────────────

    def _watch_processes(self) -> None:
        """Detect suspicious processes running inside the container."""
        while not self._should_stop():
            if self._is_paused():
                if self._sleep_interruptible(15):
                    return
                continue

            try:
                processes = self.dm.get_top()
                for proc in processes:
                    cmd = proc.get("CMD", proc.get("COMMAND", ""))
                    base_cmd = cmd.split()[0].split("/")[-1] if cmd else ""

                    if base_cmd in SUSPICIOUS_PROCESSES:
                        self.alerts.fire(
                            "CRITICAL",
                            "processes",
                            f"Suspicious process detected: {cmd}",
                        )
                        self._auto_pause(f"Suspicious process: {base_cmd}")

            except (NotFound, APIError) as e:
                logger.debug("Process watcher Docker error: %s", e)
            except Exception as e:
                self.alerts.fire("WARNING", "monitor", f"Process watcher error: {e}")
                logger.exception("Unexpected error in process watcher")

            if self._sleep_interruptible(15):
                return

    # ── 3. Network connection auditor ────────────────────────────────

    def _watch_network(self) -> None:
        """Audit network connections inside the container."""
        whitelisted_addrs = {"127.0.0.1", "0.0.0.0", "::1", "::"}
        seen_remotes: set = set()

        while not self._should_stop():
            if self._is_paused():
                if self._sleep_interruptible(30):
                    return
                continue

            try:
                if self.dm.get_status() != "running":
                    if self._sleep_interruptible(30):
                        return
                    continue

                output = self.dm.exec_run("ss -tunp")
                for line in output.splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 5:
                        remote = parts[4]
                        addr = remote.rsplit(":", 1)[0] if ":" in remote else remote
                        addr = addr.strip("[]")

                        if (
                            addr not in whitelisted_addrs
                            and addr != "*"
                            and remote not in seen_remotes
                        ):
                            seen_remotes.add(remote)
                            self.alerts.fire(
                                "WARNING",
                                "network",
                                f"New outbound connection to {remote}",
                            )

            except (NotFound, APIError, RuntimeError) as e:
                logger.debug("Network watcher Docker error: %s", e)
            except Exception as e:
                self.alerts.fire("WARNING", "monitor", f"Network watcher error: {e}")
                logger.exception("Unexpected error in network watcher")

            if self._sleep_interruptible(30):
                return

    # ── 4. Log pattern scanner ───────────────────────────────────────

    def _watch_logs(self) -> None:
        """Scan container logs in real-time for suspicious patterns."""
        try:
            for line in self.dm.get_logs(follow=True, tail=0):
                if self._should_stop():
                    return

                for pattern, severity, description in LOG_PATTERNS:
                    if re.search(pattern, line):
                        short_line = line[:200] + "..." if len(line) > 200 else line
                        self.alerts.fire(
                            severity,
                            "logs",
                            f"{description}: {short_line}",
                        )
                        break

        except (NotFound, APIError) as e:
            logger.debug("Log watcher Docker error: %s", e)
        except Exception as e:
            self.alerts.fire("WARNING", "monitor", f"Log watcher error: {e}")
            logger.exception("Unexpected error in log watcher")

    # ── 5. Health checker ────────────────────────────────────────────

    def _watch_health(self) -> None:
        """Monitor Docker healthcheck status."""
        while not self._should_stop():
            if self._is_paused():
                if self._sleep_interruptible(30):
                    return
                continue

            try:
                health = self.dm.get_health()
                if health == "unhealthy":
                    self._consecutive_unhealthy += 1
                    if self._consecutive_unhealthy >= 2:
                        count = self._consecutive_unhealthy
                        self.alerts.fire(
                            "CRITICAL",
                            "health",
                            f"Container unhealthy ({count} consecutive checks)",
                        )
                        self._auto_pause("Container unhealthy")
                else:
                    self._consecutive_unhealthy = 0

            except (NotFound, APIError) as e:
                logger.debug("Health watcher Docker error: %s", e)
            except Exception as e:
                self.alerts.fire("WARNING", "monitor", f"Health watcher error: {e}")
                logger.exception("Unexpected error in health watcher")

            if self._sleep_interruptible(30):
                return

    # ── 6. Docker event listener ─────────────────────────────────────

    def _watch_events(self) -> None:
        """Listen for Docker lifecycle events on the crabpot container."""
        try:
            for event in self.dm.events_stream():
                if self._should_stop():
                    return

                action = event.get("Action", event.get("status", ""))

                if action in CRITICAL_EVENTS:
                    self.alerts.fire(
                        "CRITICAL",
                        "events",
                        f"Container event: {action}",
                    )
                elif action in WARNING_EVENTS:
                    self.alerts.fire(
                        "WARNING",
                        "events",
                        f"Container event: {action}",
                    )
                elif action == "start":
                    self.alerts.fire("INFO", "events", "Container started")

        except (NotFound, APIError) as e:
            logger.debug("Event watcher Docker error: %s", e)
        except Exception as e:
            self.alerts.fire("WARNING", "monitor", f"Event watcher error: {e}")
            logger.exception("Unexpected error in event watcher")
