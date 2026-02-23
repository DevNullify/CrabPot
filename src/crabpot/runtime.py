"""Runtime abstraction layer for CrabPot.

Provides a common interface for both Docker and WSL2 deployment targets,
allowing command handlers to be target-agnostic.
"""

from abc import ABC, abstractmethod
from typing import Iterator, Optional


class Runtime(ABC):
    """Abstract base class for CrabPot deployment runtimes."""

    @abstractmethod
    def setup(self) -> None:
        """Perform initial setup (build image, create distro, etc.)."""

    @abstractmethod
    def start(self) -> None:
        """Start the runtime environment."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the runtime environment gracefully."""

    @abstractmethod
    def pause(self) -> None:
        """Freeze the runtime (zero CPU, memory preserved)."""

    @abstractmethod
    def resume(self) -> None:
        """Unfreeze a paused runtime."""

    @abstractmethod
    def destroy(self) -> None:
        """Full teardown — remove all resources."""

    @abstractmethod
    def get_status(self) -> str:
        """Get current status: running, paused, exited, not_found."""

    @abstractmethod
    def stats_snapshot(self) -> Optional[dict]:
        """Get a snapshot of resource usage stats."""

    @abstractmethod
    def get_top(self) -> list:
        """Get the process list inside the runtime."""

    @abstractmethod
    def exec_run(self, cmd: str) -> str:
        """Execute a command inside the runtime, return stdout."""

    @abstractmethod
    def get_logs(self, follow: bool = False, tail: int = 100) -> Iterator[str]:
        """Stream or tail logs."""

    @abstractmethod
    def events_stream(self) -> Iterator[dict]:
        """Stream lifecycle events."""

    @abstractmethod
    def get_health(self) -> Optional[str]:
        """Get health status."""

    @abstractmethod
    def get_start_time(self) -> Optional[str]:
        """Get the start time as an ISO string."""

    @abstractmethod
    def open_shell(self) -> None:
        """Open an interactive shell into the runtime."""

    @abstractmethod
    def build(self) -> None:
        """Build the runtime image/environment."""

    @abstractmethod
    def is_running(self) -> bool:
        """Check if the runtime is currently running."""


class DockerRuntime(Runtime):
    """Wraps DockerManager to satisfy the Runtime interface."""

    def __init__(self, docker_manager):
        self.dm = docker_manager

    def setup(self) -> None:
        self.dm.build()

    def start(self) -> None:
        self.dm.start()

    def stop(self) -> None:
        self.dm.stop()

    def pause(self) -> None:
        self.dm.pause()

    def resume(self) -> None:
        self.dm.resume()

    def destroy(self) -> None:
        self.dm.destroy()

    def get_status(self) -> str:
        return self.dm.get_status()

    def stats_snapshot(self) -> Optional[dict]:
        return self.dm.stats_snapshot()

    def get_top(self) -> list:
        return self.dm.get_top()

    def exec_run(self, cmd: str) -> str:
        return self.dm.exec_run(cmd)

    def get_logs(self, follow: bool = False, tail: int = 100) -> Iterator[str]:
        return self.dm.get_logs(follow=follow, tail=tail)

    def events_stream(self) -> Iterator[dict]:
        return self.dm.events_stream()

    def get_health(self) -> Optional[str]:
        return self.dm.get_health()

    def get_start_time(self) -> Optional[str]:
        return self.dm.get_start_time()

    def open_shell(self) -> None:
        import subprocess
        subprocess.run(["docker", "exec", "-it", "crabpot", "/bin/sh"], check=False)

    def build(self) -> None:
        self.dm.build()

    def is_running(self) -> bool:
        return self.dm.is_running()


class WSL2Runtime(Runtime):
    """Wraps WSL2Manager to satisfy the Runtime interface.

    All operations delegate to the underlying WSL2Manager. If no manager
    is provided, operations raise NotImplementedError.
    """

    def __init__(self, wsl2_manager=None):
        self.wm = wsl2_manager

    def _require_manager(self):
        if self.wm is None:
            raise NotImplementedError("WSL2 runtime requires a WSL2Manager instance")

    def setup(self) -> None:
        self._require_manager()
        self.wm.create_distro()

    def start(self) -> None:
        self._require_manager()
        self.wm.start()

    def stop(self) -> None:
        self._require_manager()
        self.wm.stop()

    def pause(self) -> None:
        self._require_manager()
        self.wm.stop()  # WSL2 doesn't have pause — terminate instead

    def resume(self) -> None:
        self._require_manager()
        self.wm.start()

    def destroy(self) -> None:
        self._require_manager()
        self.wm.destroy()

    def get_status(self) -> str:
        self._require_manager()
        return self.wm.get_status()

    def stats_snapshot(self) -> Optional[dict]:
        self._require_manager()
        return self.wm.get_stats()

    def get_top(self) -> list:
        self._require_manager()
        output = self.wm.exec_run("ps aux")
        lines = output.strip().splitlines()
        if len(lines) <= 1:
            return []
        return [{"CMD": line.split(None, 10)[-1]} for line in lines[1:]]

    def exec_run(self, cmd: str) -> str:
        self._require_manager()
        return self.wm.exec_run(cmd)

    def get_logs(self, follow: bool = False, tail: int = 100) -> Iterator[str]:
        self._require_manager()
        return self.wm.get_logs(follow=follow, tail=tail)

    def events_stream(self) -> Iterator[dict]:
        # WSL2 doesn't have a native event stream
        return iter([])

    def get_health(self) -> Optional[str]:
        self._require_manager()
        status = self.wm.get_status()
        return "healthy" if status == "running" else "unhealthy"

    def get_start_time(self) -> Optional[str]:
        return None  # WSL2 doesn't expose start time easily

    def open_shell(self) -> None:
        self._require_manager()
        self.wm.open_shell()

    def build(self) -> None:
        self.setup()

    def is_running(self) -> bool:
        self._require_manager()
        return self.wm.get_status() == "running"
