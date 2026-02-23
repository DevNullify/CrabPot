"""WSL2 distribution manager for CrabPot.

Manages a WSL2 distribution as an alternative to Docker containers.
Provides import, start, stop, destroy, and exec operations via wsl.exe.
"""

import logging
import subprocess
from pathlib import Path
from typing import Iterator, Optional

from jinja2 import BaseLoader, Environment

from crabpot.config import CrabPotConfig
from crabpot.paths import WSL2_DIR
from crabpot.security_presets import ResourceProfile, SecurityProfile

logger = logging.getLogger(__name__)


class WSL2Manager:
    """Manages a CrabPot WSL2 distribution lifecycle."""

    def __init__(
        self,
        distro_name: str = "CrabPot",
        wsl2_dir: Path = WSL2_DIR,
    ):
        self.distro_name = distro_name
        self.wsl2_dir = wsl2_dir
        self.jinja_env = Environment(loader=BaseLoader(), keep_trailing_newline=True)

    def create_distro(
        self,
        config: Optional[CrabPotConfig] = None,
        security_profile: Optional[SecurityProfile] = None,
        resource_profile: Optional[ResourceProfile] = None,
    ) -> None:
        """Create and configure a WSL2 distribution.

        Steps:
            1. Prepare rootfs (download or extract from Docker image)
            2. Import as WSL2 distribution
            3. Apply security hardening
            4. Install OpenClaw
        """
        self.wsl2_dir.mkdir(parents=True, exist_ok=True)
        rootfs_path = self._prepare_rootfs(config)
        self._import_distro(rootfs_path)

        if security_profile:
            self._apply_security(security_profile, resource_profile)

    def start(self) -> None:
        """Start the WSL2 distribution."""
        subprocess.run(
            ["wsl", "-d", self.distro_name, "--exec", "/bin/true"],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("WSL2 distribution '%s' started", self.distro_name)

    def stop(self) -> None:
        """Terminate the WSL2 distribution."""
        subprocess.run(
            ["wsl", "-t", self.distro_name],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("WSL2 distribution '%s' terminated", self.distro_name)

    def destroy(self) -> None:
        """Unregister and remove the WSL2 distribution."""
        subprocess.run(
            ["wsl", "--unregister", self.distro_name],
            check=False,
            capture_output=True,
            text=True,
        )
        # Clean up local files
        if self.wsl2_dir.exists():
            import shutil
            shutil.rmtree(self.wsl2_dir, ignore_errors=True)
        logger.info("WSL2 distribution '%s' destroyed", self.distro_name)

    def get_status(self) -> str:
        """Get distribution status: running, stopped, or not_found."""
        try:
            result = subprocess.run(
                ["wsl", "-l", "-v"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return "not_found"

            for line in result.stdout.splitlines():
                # WSL output may have unicode markers; strip them
                clean = line.replace("\x00", "").strip()
                if self.distro_name in clean:
                    if "Running" in clean:
                        return "running"
                    elif "Stopped" in clean:
                        return "stopped"
                    return "stopped"

            return "not_found"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "not_found"

    def exec_run(self, cmd: str) -> str:
        """Execute a command inside the WSL2 distribution."""
        result = subprocess.run(
            ["wsl", "-d", self.distro_name, "--exec", "sh", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout

    def get_logs(self, follow: bool = False, tail: int = 100) -> Iterator[str]:
        """Get OpenClaw logs from the WSL2 distribution."""
        cmd = f"journalctl -u crabpot-openclaw --no-pager -n {tail}"
        output = self.exec_run(cmd)
        yield from output.splitlines()

    def get_stats(self) -> Optional[dict]:
        """Get basic resource stats from WSL2."""
        try:
            # Get memory info
            mem_output = self.exec_run("cat /proc/meminfo")
            mem_total = 0
            mem_available = 0
            for line in mem_output.splitlines():
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1]) * 1024  # kB to bytes
                elif line.startswith("MemAvailable:"):
                    mem_available = int(line.split()[1]) * 1024

            mem_used = mem_total - mem_available
            mem_pct = (mem_used / mem_total * 100) if mem_total > 0 else 0

            # Get CPU from /proc/loadavg (1-min average as rough %)
            load_output = self.exec_run("cat /proc/loadavg")
            load_1m = float(load_output.split()[0]) if load_output.strip() else 0

            # Get PID count
            pids_output = self.exec_run("ls /proc | grep -c '^[0-9]'")
            pids = int(pids_output.strip()) if pids_output.strip() else 0

            return {
                "cpu_percent": round(load_1m * 100, 1),
                "memory_usage": mem_used,
                "memory_limit": mem_total,
                "memory_percent": round(mem_pct, 1),
                "network_rx": 0,
                "network_tx": 0,
                "pids": pids,
                "timestamp": "",
            }
        except Exception as e:
            logger.debug("Failed to get WSL2 stats: %s", e)
            return None

    def open_shell(self) -> None:
        """Open an interactive shell into the WSL2 distribution."""
        subprocess.run(["wsl", "-d", self.distro_name], check=False)

    # ── Internal helpers ───────────────────────────────────────────

    def _prepare_rootfs(self, config: Optional[CrabPotConfig] = None) -> Path:
        """Prepare a rootfs tarball for WSL2 import.

        For source=image: exports from Docker image.
        For source=build: downloads base Ubuntu rootfs.
        """
        rootfs_path = self.wsl2_dir / "rootfs.tar"

        if config and config.openclaw.source == "image":
            image = f"openclaw/openclaw:{config.openclaw.image_tag}"
            subprocess.run(
                ["docker", "create", "--name", "crabpot-export", image],
                check=True,
                capture_output=True,
                text=True,
            )
            try:
                subprocess.run(
                    ["docker", "export", "-o", str(rootfs_path), "crabpot-export"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            finally:
                subprocess.run(
                    ["docker", "rm", "crabpot-export"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
        else:
            # Use a minimal Ubuntu rootfs
            base_image = config.wsl2.base_image if config else "ubuntu:22.04"
            subprocess.run(
                ["docker", "create", "--name", "crabpot-export", base_image],
                check=True,
                capture_output=True,
                text=True,
            )
            try:
                subprocess.run(
                    ["docker", "export", "-o", str(rootfs_path), "crabpot-export"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            finally:
                subprocess.run(
                    ["docker", "rm", "crabpot-export"],
                    check=False,
                    capture_output=True,
                    text=True,
                )

        return rootfs_path

    def _import_distro(self, rootfs_path: Path) -> None:
        """Import a rootfs tarball as a WSL2 distribution."""
        install_dir = self.wsl2_dir / "install"
        install_dir.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            [
                "wsl", "--import", self.distro_name,
                str(install_dir), str(rootfs_path),
                "--version", "2",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Imported WSL2 distribution '%s'", self.distro_name)

    def _apply_security(
        self,
        profile: SecurityProfile,
        resource_profile: Optional[ResourceProfile] = None,
    ) -> None:
        """Apply security hardening inside the WSL2 distribution."""
        templates_dir = Path(__file__).parent / "templates"

        # Render setup script
        setup_template = (templates_dir / "wsl2-setup.sh.j2").read_text()
        template = self.jinja_env.from_string(setup_template)

        from dataclasses import asdict
        context = asdict(profile)
        if resource_profile:
            context.update(asdict(resource_profile))

        setup_script = template.render(**context)

        # Write and execute the setup script
        script_path = self.wsl2_dir / "setup.sh"
        script_path.write_text(setup_script)

        self.exec_run(f"bash {script_path}")

        # Render and install systemd service
        service_template = (templates_dir / "wsl2-crabpot.service.j2").read_text()
        template = self.jinja_env.from_string(service_template)
        service_content = template.render(**context)

        service_path = self.wsl2_dir / "crabpot-openclaw.service"
        service_path.write_text(service_content)

        self.exec_run(
            f"cp {service_path} /etc/systemd/system/crabpot-openclaw.service && "
            "systemctl daemon-reload && systemctl enable crabpot-openclaw"
        )
