# Getting Started

This guide walks you through installing CrabPot, configuring your first OpenClaw sandbox, and running it securely.

## Prerequisites

- **Linux** or **WSL2** on Windows 10/11
- **Docker Engine** (20.10+) with the Compose plugin
- **Python 3.9+** with `venv` support

If you're on WSL2, make sure Docker Desktop is installed and WSL integration is enabled, or install Docker Engine directly inside your WSL2 distribution.

## Installation

### One-Liner (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/DevNullify/crabpot/main/install.sh | sh
```

This script will:

1. Verify you're on Linux/WSL2
2. Install Docker if not present (via official apt repository)
3. Install Python 3 if not present
4. Create `~/.crabpot/` directory structure
5. Set up a Python virtual environment
6. Install the `crabpot` package
7. Add `~/.crabpot/bin` to your PATH

After installation, restart your shell or run:

```bash
export PATH="$HOME/.crabpot/bin:$PATH"
```

### Manual Installation (Development)

```bash
git clone https://github.com/DevNullify/crabpot.git
cd crabpot
pip install -e ".[dev]"
```

## First Run

### Step 1: Initialize

```bash
crabpot init
```

This verifies that Docker is installed, the daemon is running, and Docker Compose is available. It also creates the CrabPot data directories.

**Expected output:**
```
CrabPot v1.0.0 — Checking prerequisites...

Docker: Docker version 24.0.7, build afdd53b
Docker daemon: running
Docker Compose: available
CrabPot home: /home/user/.crabpot

All prerequisites satisfied.
Next: crabpot setup
```

### Step 2: Setup

```bash
crabpot setup
```

This generates the hardened Docker configuration and builds the container image. The first build downloads the OpenClaw base image and applies security hardening, which may take a few minutes.

**What gets generated in `~/.crabpot/config/`:**
- `docker-compose.yml` — Hardened container configuration
- `Dockerfile.crabpot` — Security-stripped image build
- `seccomp-profile.json` — System call whitelist (~120 allowed)
- `.env` — OpenClaw environment variables (API keys, etc.)

### Step 3: Configure API Keys

Edit `~/.crabpot/config/.env` to add your API keys:

```bash
# Example
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

### Step 4: Launch

```bash
crabpot start
```

This starts the container, the security monitor (6 channels), and the web dashboard. You'll see:

```
Starting CrabPot...

Starting container...
Container started.
Starting security monitor (6 channels)...
Security monitor active.
Starting web dashboard...
Dashboard running.

CrabPot is running!
  OpenClaw Gateway: http://localhost:18789
  CrabPot Dashboard: http://localhost:9876
  TUI: crabpot tui

Press Ctrl+C to stop.
```

## Daily Usage

```bash
crabpot start         # Launch everything
crabpot status        # Quick health check
crabpot tui           # Interactive terminal dashboard
crabpot pause         # Freeze when not in use (saves CPU)
crabpot resume        # Unfreeze to continue
crabpot logs -f       # Follow container logs
crabpot stop          # Graceful shutdown
```

## Accessing OpenClaw

Once running, open your browser to:

- **OpenClaw Gateway**: [http://localhost:18789](http://localhost:18789)
- **CrabPot Dashboard**: [http://localhost:9876](http://localhost:9876)

The Gateway UI is OpenClaw's web interface where you connect messaging platforms. The CrabPot Dashboard shows real-time resource usage, security alerts, and container controls.

## Configuration

### Resource Limits

The default limits are:
- **CPU**: 2 cores
- **Memory**: 2 GB
- **PIDs**: 200 processes

To customize, edit `~/.crabpot/config/docker-compose.yml` under the `deploy.resources` section, then restart with `crabpot stop && crabpot start`.

### Ports

| Port | Service | Binding |
|------|---------|---------|
| 18789 | OpenClaw Gateway | `127.0.0.1` (localhost only) |
| 9876 | CrabPot Dashboard | `127.0.0.1` (localhost only) |

Both ports are bound to localhost only and are not accessible from outside your machine.

## Cleanup

```bash
crabpot destroy       # Remove container, volumes, and configs
crabpot uninstall     # Remove CrabPot entirely
```

`destroy` removes the container and Docker volumes but preserves the `~/.crabpot/config/.env` file (your API keys).

`uninstall` removes everything, including `~/.crabpot/`. You'll need to manually remove the PATH entry from your shell config.

## Troubleshooting

### Docker daemon not running

```bash
sudo systemctl start docker
# or on WSL2 with Docker Desktop:
# Make sure Docker Desktop is running on Windows
```

### Permission denied for Docker

```bash
sudo usermod -aG docker $USER
# Then log out and back in
```

### Container won't start

Check if the port is already in use:

```bash
ss -tlnp | grep 18789
```

Check container logs:

```bash
docker logs crabpot
```

### Dashboard not loading

Make sure port 9876 isn't already in use:

```bash
ss -tlnp | grep 9876
```
