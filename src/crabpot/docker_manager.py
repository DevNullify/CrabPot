"""Docker SDK wrapper for managing the CrabPot container lifecycle."""

import contextlib
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Optional

import docker
from docker.errors import APIError, NotFound

from crabpot.paths import CONFIG_DIR, CONTAINER_NAME


class DockerManager:
    """Manages the CrabPot Docker container lifecycle via the Docker SDK."""

    def __init__(self, config_dir: Path = CONFIG_DIR):
        self.client = docker.from_env()
        self.container_name = CONTAINER_NAME
        self.config_dir = config_dir

    def build(self) -> None:
        """Build the hardened container image using docker compose."""
        compose_file = self.config_dir / "docker-compose.yml"
        if not compose_file.exists():
            raise FileNotFoundError(
                f"docker-compose.yml not found at {compose_file}. Run 'crabpot setup' first."
            )
        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "build"],
            cwd=str(self.config_dir),
            check=True,
        )

    def start(self) -> None:
        """Start the CrabPot container via docker compose."""
        compose_file = self.config_dir / "docker-compose.yml"
        if not compose_file.exists():
            raise FileNotFoundError(
                f"docker-compose.yml not found at {compose_file}. Run 'crabpot setup' first."
            )

        status = self.get_status()
        if status == "running":
            return
        if status == "paused":
            self.resume()
            return

        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "up", "-d"],
            cwd=str(self.config_dir),
            check=True,
        )

    def stop(self) -> None:
        """Stop the CrabPot container gracefully."""
        container = self._get_container()
        if container is None:
            return
        if container.status == "paused":
            container.unpause()
        container.stop(timeout=30)

    def pause(self) -> None:
        """Freeze the container using cgroups freezer (zero CPU, memory preserved)."""
        container = self._get_container()
        if container is None:
            raise RuntimeError("Container is not running")
        if container.status != "running":
            raise RuntimeError(f"Cannot pause container in '{container.status}' state")
        container.pause()

    def resume(self) -> None:
        """Unfreeze a paused container."""
        container = self._get_container()
        if container is None:
            raise RuntimeError("Container not found")
        if container.status != "paused":
            raise RuntimeError(f"Container is not paused (status: {container.status})")
        container.unpause()

    def destroy(self) -> None:
        """Full teardown: stop container, remove volumes, and prune."""
        compose_file = self.config_dir / "docker-compose.yml"
        if compose_file.exists():
            subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "down", "-v", "--remove-orphans"],
                cwd=str(self.config_dir),
                check=False,
            )
        else:
            container = self._get_container()
            if container:
                with contextlib.suppress(APIError):
                    container.stop(timeout=10)
                with contextlib.suppress(APIError):
                    container.remove(v=True, force=True)

    def is_running(self) -> bool:
        """Check if the container is currently running."""
        return self.get_status() == "running"

    def get_status(self) -> str:
        """Get container status: running, paused, exited, created, or not_found."""
        container = self._get_container()
        if container is None:
            return "not_found"
        return str(container.status)

    def stats_stream(self) -> Iterator[dict]:
        """Yield parsed stats dicts from the Docker stats API (streaming)."""
        container = self._get_container()
        if container is None:
            return
        for raw in container.stats(stream=True, decode=True):
            yield self._parse_stats(raw)

    def stats_snapshot(self) -> Optional[dict]:
        """Get a single stats snapshot."""
        container = self._get_container()
        if container is None:
            return None
        raw = container.stats(stream=False)
        return self._parse_stats(raw)

    def get_top(self) -> list:
        """Get the process list inside the container."""
        container = self._get_container()
        if container is None:
            return []
        try:
            result = container.top()
            processes = []
            titles = result.get("Titles", [])
            for proc in result.get("Processes", []):
                processes.append(dict(zip(titles, proc)))
            return processes
        except APIError:
            return []

    def exec_run(self, cmd: str) -> str:
        """Execute a command in the container, return stdout."""
        container = self._get_container()
        if container is None:
            raise RuntimeError("Container is not running")
        exit_code, output = container.exec_run(cmd, demux=True)
        stdout = output[0].decode() if output[0] else ""
        return stdout

    def get_logs(self, follow: bool = False, tail: int = 100) -> Iterator[str]:
        """Stream or tail container logs."""
        container = self._get_container()
        if container is None:
            return

        kwargs = {"stream": True, "follow": follow, "tail": tail, "timestamps": True}
        for chunk in container.logs(**kwargs):
            yield chunk.decode("utf-8", errors="replace").rstrip("\n")

    def get_container(self):
        """Get the Docker container object (public accessor)."""
        return self._get_container()

    def get_start_time(self) -> Optional[str]:
        """Get the container's start time as an ISO string."""
        container = self._get_container()
        if container is None:
            return None
        container.reload()
        state = container.attrs.get("State", {})
        started: Optional[str] = state.get("StartedAt")
        return started

    def get_health(self) -> Optional[str]:
        """Get the container's health status."""
        container = self._get_container()
        if container is None:
            return None
        container.reload()
        state = container.attrs.get("State", {})
        health = state.get("Health", {})
        result: Optional[str] = health.get("Status", "none")
        return result

    def events_stream(self) -> Iterator[dict]:
        """Stream Docker events filtered to the crabpot container."""
        yield from self.client.events(
            decode=True,
            filters={"container": self.container_name},
        )

    def _get_container(self):
        """Get the container object, or None if not found."""
        try:
            return self.client.containers.get(self.container_name)
        except NotFound:
            return None

    @staticmethod
    def _parse_stats(raw: dict) -> dict:
        """Parse raw Docker stats into a clean dict."""
        cpu_delta = raw.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0) - raw.get(
            "precpu_stats", {}
        ).get("cpu_usage", {}).get("total_usage", 0)
        system_delta = raw.get("cpu_stats", {}).get("system_cpu_usage", 0) - raw.get(
            "precpu_stats", {}
        ).get("system_cpu_usage", 0)
        num_cpus = raw.get("cpu_stats", {}).get("online_cpus", 1)

        cpu_percent = 0.0
        if system_delta > 0:
            cpu_percent = (cpu_delta / system_delta) * num_cpus * 100.0

        mem_usage = raw.get("memory_stats", {}).get("usage", 0)
        mem_limit = raw.get("memory_stats", {}).get("limit", 1)
        mem_percent = (mem_usage / mem_limit) * 100.0 if mem_limit > 0 else 0.0

        networks = raw.get("networks", {})
        net_rx = sum(iface.get("rx_bytes", 0) for iface in networks.values())
        net_tx = sum(iface.get("tx_bytes", 0) for iface in networks.values())

        pids = raw.get("pids_stats", {}).get("current", 0)

        return {
            "cpu_percent": round(cpu_percent, 1),
            "memory_usage": mem_usage,
            "memory_limit": mem_limit,
            "memory_percent": round(mem_percent, 1),
            "network_rx": net_rx,
            "network_tx": net_tx,
            "pids": pids,
            "timestamp": raw.get("read", ""),
        }

    @staticmethod
    def check_docker() -> dict:
        """Verify Docker is installed and the daemon is running."""
        info = {"installed": False, "running": False, "compose": False, "version": ""}

        try:
            result = subprocess.run(
                ["docker", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                info["installed"] = True
                info["version"] = result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return info

        try:
            client = docker.from_env()
            client.ping()
            info["running"] = True
        except Exception:
            return info

        try:
            result = subprocess.run(
                ["docker", "compose", "version"], capture_output=True, text=True, timeout=5
            )
            info["compose"] = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return info
