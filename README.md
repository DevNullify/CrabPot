# CrabPot

**Secure OpenClaw Sandbox for WSL2**

[![CI](https://github.com/DevNullify/crabpot/actions/workflows/ci.yml/badge.svg)](https://github.com/DevNullify/crabpot/actions/workflows/ci.yml)
[![CodeQL](https://github.com/DevNullify/crabpot/actions/workflows/codeql.yml/badge.svg)](https://github.com/DevNullify/crabpot/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

OpenClaw is a powerful open-source AI assistant that connects to messaging platforms (WhatsApp, Telegram, etc.) but poses **significant security risks** when run on a personal machine -- it can execute shell commands, read/write files, and run arbitrary scripts.

CrabPot solves this by providing a **hardened, monitored sandbox** with configurable security presets, a web dashboard, and TUI. Choose between Docker containers or WSL2 native distributions as your runtime target, pick a security level that fits your needs, and manage everything through the `crabpot` CLI.

---

## Quick Start

```bash
# Install (one-liner)
curl -fsSL https://raw.githubusercontent.com/DevNullify/crabpot/main/install.sh | sh

# Interactive setup wizard
crabpot init      # Choose target (Docker/WSL2), security preset, OpenClaw version

# Launch
crabpot start     # Launch everything with your chosen configuration
```

`crabpot init` walks you through target selection (Docker or WSL2), security level (minimal, standard, or paranoid), and OpenClaw version (latest, a pinned tag like v1.2.3, etc.). Your choices are saved to `~/.crabpot/crabpot.yml` and can be changed at any time with `crabpot config`.

Your OpenClaw instance is now running at `http://localhost:18789` with a security dashboard at `http://localhost:9876`.

---

## Features

| Feature | Description |
|---------|-------------|
| **Configurable Security Presets** | Three levels -- minimal, standard, paranoid -- with per-feature overrides |
| **Docker + WSL2 Targets** | Run OpenClaw in a hardened Docker container or a locked-down WSL2 distribution |
| **YAML Configuration** | All settings in `~/.crabpot/crabpot.yml`; edit directly or via `crabpot config` |
| **Interactive Init Wizard** | `crabpot init` guides you through target, security, and version selection |
| **OpenClaw Version Management** | Pin to `latest`, a specific tag (`v1.2.3`), or a custom image |
| **Web Dashboard** | Real-time stats, controls, alert feed, and log streaming at `:9876` |
| **Terminal UI** | Rich TUI with keyboard controls (`crabpot tui`) |
| **6-Channel Monitor** | CPU/memory, process watchdog, network audit, log scanning, health, runtime events |
| **Auto-Pause** | CRITICAL alerts automatically freeze the container/distribution |
| **Windows Alerts** | Toast notifications on WSL2 for critical events |
| **Policy Engine** | Define and manage security policies; approve or deny pending actions |

---

## CLI Reference

```
crabpot init          Interactive setup wizard (target, security, OpenClaw version)
crabpot start         Launch sandbox + dashboard + security monitor
crabpot stop          Graceful shutdown of all components
crabpot pause         Freeze sandbox (zero CPU, state preserved)
crabpot resume        Unfreeze sandbox
crabpot tui           Interactive terminal dashboard
crabpot status        Show current status
crabpot logs [-f]     Stream sandbox logs (-f to follow)
crabpot alerts        View alert history (--severity CRITICAL, --last 50)
crabpot shell         Open emergency shell into sandbox
crabpot destroy       Full teardown and cleanup
crabpot uninstall     Remove CrabPot completely

crabpot config        Show current configuration
crabpot config edit   Open config in $EDITOR
crabpot config reset  Reset to defaults

crabpot policy show   List active security policies
crabpot policy add    Add a custom policy rule
crabpot policy remove Remove a policy rule

crabpot approve       Approve a pending action flagged by the policy engine
crabpot deny          Deny a pending action flagged by the policy engine
crabpot audit         Show security audit log (actions, approvals, denials)
```

---

## Configuration

All settings live in `~/.crabpot/crabpot.yml`, created by `crabpot init`. Example:

```yaml
target: docker          # docker | wsl2
openclaw_version: latest  # latest, v1.2.3, etc.

security:
  preset: standard      # minimal | standard | paranoid
  overrides:            # per-feature overrides beyond the preset
    read_only_rootfs: true
    drop_capabilities: true
    seccomp_profile: true
    resource_limits:
      cpu: 2
      memory: 2GB
      pids: 200

monitor:
  auto_pause: true
  alert_channels:
    - terminal
    - websocket
    - log

dashboard:
  port: 9876
```

Edit directly, or use `crabpot config edit` / `crabpot config reset`.

---

## Security Presets

CrabPot ships with three presets. Each enables a different subset of hardening layers. Use `overrides` in the config to toggle individual features on top of any preset.

| Layer | Minimal | Standard | Paranoid |
|-------|:-------:|:--------:|:--------:|
| Read-only rootfs + tmpfs | -- | Yes | Yes |
| Non-root user (node:1000) | Yes | Yes | Yes |
| Drop ALL capabilities | -- | Yes | Yes |
| Seccomp profile (~120 syscalls) | -- | Yes | Yes |
| No-new-privileges | -- | Yes | Yes |
| Resource limits (CPU/mem/PIDs) | Relaxed | Moderate | Strict |
| Localhost-only binding | Yes | Yes | Yes |
| ICC disabled | -- | Yes | Yes |
| Remove exfil tools (curl/wget/nc) | -- | -- | Yes |
| Log rotation cap (10MB x 3) | Yes | Yes | Yes |
| 6-channel monitoring | Basic | Full | Full |
| Auto-pause on CRITICAL | -- | Yes | Yes |

**Minimal** -- low friction for development and testing. **Standard** -- recommended for daily use. **Paranoid** -- maximum lockdown for untrusted workloads.

---

## Architecture

```
                        WSL2 Host
 +---------------------------------------------------------+
 |                                                         |
 |  crabpot CLI (Python)                                   |
 |    +-- RuntimeManager (abstract)                        |
 |    |     +-- DockerBackend  (container lifecycle)        |
 |    |     +-- WSL2Backend    (distro lifecycle)           |
 |    +-- ConfigManager        (~/.crabpot/crabpot.yml)    |
 |    +-- PolicyEngine         (approve/deny/audit)        |
 |    +-- SecurityMonitor      (6 threaded watchers)       |
 |    +-- AlertDispatcher      (toast/terminal/log/WS)     |
 |    +-- DashboardServer      (Flask+SocketIO :9876)      |
 |    +-- TUI                  (Rich terminal dashboard)   |
 |                                                         |
 |  +--- Docker (isolated network) ---+  +-- WSL2 Distro -+|
 |  | OpenClaw Container (hardened)   |  | OpenClaw (locked||
 |  | 127.0.0.1:18789 -> Gateway UI  |  | down distro)   ||
 |  +---------------------------------+  +----------------+|
 +---------------------------------------------------------+
```

The `RuntimeManager` abstraction lets CrabPot manage either a Docker container or a WSL2 native distribution through the same CLI interface. The active backend is determined by the `target` setting in your config.

---

## Documentation

- **[Getting Started](docs/getting-started.md)** -- Installation, first run, configuration
- **[Security Model](docs/security.md)** -- Deep dive into presets and hardening layers
- **[Monitoring Guide](docs/monitoring.md)** -- Understanding alerts, thresholds, auto-pause
- **[Dashboard Guide](docs/dashboard.md)** -- Web dashboard features and usage
- **[Development](docs/development.md)** -- Setting up a dev environment, running tests
- **[Contributing](CONTRIBUTING.md)** -- How to contribute to CrabPot

---

## Requirements

- **Linux** or **WSL2** (Windows Subsystem for Linux 2)
- **Docker** with Docker Compose plugin (for Docker target) **or** WSL2 with `wsl.exe` (for WSL2 target)
- **Python 3.9+**

---

## License

MIT License. See [LICENSE](LICENSE) for details.
