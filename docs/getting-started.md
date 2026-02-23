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

This launches an interactive wizard that walks you through initial setup. The wizard asks:

1. **Deployment target** -- `docker` (standard Docker container) or `wsl2` (native WSL2 integration)
2. **OpenClaw image tag** -- which OpenClaw version to use (e.g. `latest`, `0.9.1`)
3. **Security preset** -- how much hardening to apply:
   - `minimal` -- basic isolation, 4 CPU cores, 4 GB memory
   - `standard` -- balanced security and performance, 2 CPU cores, 2 GB memory (recommended)
   - `paranoid` -- maximum hardening with all 12 security layers, 1 CPU core, 1 GB memory
4. **Prerequisite check** -- verifies Docker, Docker Compose, and daemon are available

Once complete, the wizard generates `~/.crabpot/crabpot.yml` with your chosen settings.

**Expected output:**
```
CrabPot v2.0.0 — Setup Wizard

[1/4] Deployment target
  > docker

[2/4] OpenClaw image tag
  > latest

[3/4] Security preset
  > standard

[4/4] Checking prerequisites...
  Docker: Docker version 24.0.7, build afdd53b
  Docker daemon: running
  Docker Compose: available

Configuration written to ~/.crabpot/crabpot.yml
Next: crabpot setup
```

#### Non-Interactive Mode

You can skip the wizard by passing all options as flags:

```bash
crabpot init --target docker --preset standard --non-interactive
```

#### WSL2 Target

To set up CrabPot with native WSL2 integration:

```bash
crabpot init --target wsl2
```

### Step 2: Setup

```bash
crabpot setup
```

This reads your `~/.crabpot/crabpot.yml` configuration, generates the Docker configs based on your chosen security preset, and builds the container image if `hardened_image` is enabled in your config. The first build downloads the OpenClaw base image and applies security hardening, which may take a few minutes.

**What gets generated in `~/.crabpot/config/`:**
- `docker-compose.yml` -- Hardened container configuration (preset-specific)
- `Dockerfile.crabpot` -- Security-stripped image build (if hardened_image is enabled)
- `seccomp-profile.json` -- System call whitelist (preset-dependent)
- `.env` -- OpenClaw environment variables (API keys, etc.)

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

CrabPot stores its configuration in `~/.crabpot/crabpot.yml`. This YAML file is created by `crabpot init` and controls all aspects of your sandbox, including the deployment target, security preset, resource limits, and image settings.

### Viewing and Editing Configuration

Use the `crabpot config` command to manage your configuration:

```bash
crabpot config show           # Display current configuration
crabpot config edit           # Open crabpot.yml in your $EDITOR
crabpot config reset          # Reset to defaults (re-runs the wizard)
```

### Security Presets

The security preset determines which hardening layers are applied and the default resource limits:

| Preset | CPU | Memory | PIDs | Hardening |
|--------|-----|--------|------|-----------|
| `minimal` | 4 cores | 4 GB | 200 | Basic isolation (dropped caps, read-only rootfs) |
| `standard` | 2 cores | 2 GB | 200 | Balanced (seccomp, no-new-privileges, network restrictions) |
| `paranoid` | 1 core | 1 GB | 100 | All 12 security layers enabled |

Not all 12 security layers are active in every preset. Choose `paranoid` if you want full hardening, or `standard` for a good balance of security and usability.

### Resource Limits

Resource limits are set by default based on your chosen preset but can be overridden in `~/.crabpot/crabpot.yml`:

```yaml
resources:
  cpus: 3
  memory: "3g"
  pids: 150
```

After editing, apply changes with `crabpot stop && crabpot setup && crabpot start`.

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
