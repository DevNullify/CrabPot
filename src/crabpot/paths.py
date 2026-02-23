"""Centralized path constants for CrabPot.

Respects the CRABPOT_HOME environment variable if set, otherwise
defaults to ~/.crabpot. All modules should import paths from here
rather than computing them independently.
"""

import os
from pathlib import Path

CRABPOT_HOME = Path(os.environ.get("CRABPOT_HOME", str(Path.home() / ".crabpot")))
CONFIG_DIR = CRABPOT_HOME / "config"
DATA_DIR = CRABPOT_HOME / "data"
CONFIG_FILE = CRABPOT_HOME / "crabpot.yml"
BUILD_DIR = CRABPOT_HOME / "build"
WSL2_DIR = CRABPOT_HOME / "wsl2"
CONTAINER_NAME = "crabpot"
EGRESS_POLICY_FILE = CONFIG_DIR / "egress-allowlist.txt"
EGRESS_PROXY_PORT = 9877
