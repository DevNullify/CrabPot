"""OpenClaw version management — image pull vs build-from-source."""

import logging
import subprocess
from pathlib import Path

from crabpot.config import OpenClawConfig
from crabpot.paths import BUILD_DIR

logger = logging.getLogger(__name__)


class OpenClawSource:
    """Resolves where the OpenClaw binary/image comes from.

    Supports two modes:
        - image: Pull a pre-built image from Docker Hub (openclaw/openclaw:<tag>)
        - build: Clone the OpenClaw repo and build from source
    """

    DEFAULT_IMAGE = "openclaw/openclaw"

    def __init__(self, config: OpenClawConfig, build_base: Path = BUILD_DIR):
        self.config = config
        self.build_base = build_base

    @property
    def image_ref(self) -> str:
        """Full image reference (e.g. 'openclaw/openclaw:v1.2.3')."""
        return f"{self.DEFAULT_IMAGE}:{self.config.image_tag}"

    def resolve_for_docker(self) -> dict:
        """Resolve the OpenClaw source for Docker deployment.

        Returns:
            dict with keys:
                mode: 'pull' or 'build'
                image: full image reference (pull mode)
                context: path to build context (build mode)
        """
        if self.config.source == "image":
            return {
                "mode": "pull",
                "image": self.image_ref,
            }

        # Build from source
        repo_dir = self._ensure_cloned()
        return {
            "mode": "build",
            "context": str(repo_dir),
        }

    def resolve_for_wsl2(self) -> dict:
        """Resolve the OpenClaw source for WSL2 deployment.

        Returns:
            dict with keys:
                mode: 'extract' or 'build'
                image: full image reference (extract mode)
                repo_dir: path to cloned repo (build mode)
        """
        if self.config.source == "image":
            return {
                "mode": "extract",
                "image": self.image_ref,
            }

        repo_dir = self._ensure_cloned()
        return {
            "mode": "build",
            "repo_dir": str(repo_dir),
        }

    def _ensure_cloned(self) -> Path:
        """Clone or update the OpenClaw repository.

        Returns the path to the local clone.
        """
        self.build_base.mkdir(parents=True, exist_ok=True)
        repo_dir = self.build_base / "openclaw"

        if repo_dir.exists() and (repo_dir / ".git").exists():
            self._update_repo(repo_dir)
        else:
            self._clone_repo(repo_dir)

        return repo_dir

    def _clone_repo(self, repo_dir: Path) -> None:
        """Clone the OpenClaw repository."""
        logger.info("Cloning %s into %s", self.config.repo_url, repo_dir)
        subprocess.run(
            ["git", "clone", self.config.repo_url, str(repo_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        self._checkout_ref(repo_dir)

    def _update_repo(self, repo_dir: Path) -> None:
        """Fetch latest and checkout the configured ref."""
        logger.info("Updating repo at %s", repo_dir)
        subprocess.run(
            ["git", "fetch", "--all"],
            cwd=str(repo_dir),
            check=True,
            capture_output=True,
            text=True,
        )
        self._checkout_ref(repo_dir)

    def _checkout_ref(self, repo_dir: Path) -> None:
        """Checkout the configured branch/tag/commit."""
        subprocess.run(
            ["git", "checkout", self.config.repo_ref],
            cwd=str(repo_dir),
            check=True,
            capture_output=True,
            text=True,
        )
