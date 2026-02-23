# CrabPot

**Secure OpenClaw Sandbox for WSL2**

[![CI](https://github.com/DevNullify/crabpot/actions/workflows/ci.yml/badge.svg)](https://github.com/DevNullify/crabpot/actions/workflows/ci.yml)
[![CodeQL](https://github.com/DevNullify/crabpot/actions/workflows/codeql.yml/badge.svg)](https://github.com/DevNullify/crabpot/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

OpenClaw is a powerful open-source AI assistant that connects to messaging platforms (WhatsApp, Telegram, etc.) but poses **significant security risks** when run on a personal machine — it can execute shell commands, read/write files, and run arbitrary scripts.

CrabPot solves this by providing a **hardened, monitored Docker sandbox** with a web dashboard and TUI. Install with one command, manage everything through the `crabpot` CLI.

---

## Quick Start

```bash
# Install (one-liner)
curl -fsSL https://raw.githubusercontent.com/DevNullify/crabpot/main/install.sh | sh

# Initialize and launch
crabpot init      # Check Docker + prerequisites
crabpot setup     # Build hardened image
crabpot start     # Launch everything
```

Your OpenClaw instance is now running at `http://localhost:18789` with a security dashboard at `http://localhost:9876`.

---

## Features

| Feature | Description |
|---------|-------------|
| **12-Layer Security** | Read-only rootfs, dropped capabilities, seccomp, resource limits, and more |
| **Web Dashboard** | Real-time stats, controls, alert feed, and log streaming at `:9876` |
| **Terminal UI** | Rich TUI with keyboard controls (`crabpot tui`) |
| **6-Channel Monitor** | CPU/memory, process watchdog, network audit, log scanning, health, Docker events |
| **Auto-Pause** | CRITICAL alerts automatically freeze the container |
| **Windows Alerts** | Toast notifications on WSL2 for critical events |
| **Pause/Resume** | Freeze container to zero CPU while preserving memory state |

---

## CLI Reference

```
crabpot init          Check/install prerequisites (Docker, Python deps)
crabpot setup         Build hardened image, generate configs, run onboarding
crabpot start         Launch container + dashboard + security monitor
crabpot stop          Graceful shutdown of all components
crabpot pause         Freeze container (zero CPU, memory preserved)
crabpot resume        Unfreeze container
crabpot tui           Interactive terminal dashboard
crabpot status        Show current status
crabpot logs [-f]     Stream container logs (-f to follow)
crabpot alerts        View alert history (--severity CRITICAL, --last 50)
crabpot shell         Open emergency shell into container
crabpot destroy       Full teardown and cleanup
crabpot uninstall     Remove CrabPot completely
```

---

## Security Hardening

CrabPot applies **12 security layers** to the OpenClaw container:

| # | Layer | Mechanism | Prevents |
|---|-------|-----------|----------|
| 1 | Filesystem | Read-only rootfs + tmpfs | Malware persistence |
| 2 | User | Non-root (node:1000) | Privilege escalation |
| 3 | Capabilities | Drop ALL + NET_BIND_SERVICE | Kernel exploits |
| 4 | Seccomp | ~120 allowed syscalls | ptrace/mount/reboot |
| 5 | No-new-privileges | security_opt | SUID/SGID escalation |
| 6 | Resources | CPU=2, Mem=2GB, PIDs=200 | DoS, fork bombs |
| 7 | Network | Localhost-only binding | External access |
| 8 | Network | ICC disabled | Lateral movement |
| 9 | Image | Remove curl/wget/nc/ssh/apt | Exfiltration tools |
| 10 | Logging | 10MB x 3 cap | Disk exhaustion |
| 11 | Monitoring | 6-thread daemon | Anomaly detection |
| 12 | Auto-pause | CRITICAL -> freeze | Contain threats |

---

## Architecture

```
                        WSL2 Host
 ┌─────────────────────────────────────────────────────┐
 │                                                     │
 │  crabpot CLI (Python)                               │
 │    ├── DockerManager  (container lifecycle)          │
 │    ├── SecurityMonitor (6 threaded watchers)         │
 │    ├── AlertDispatcher (toast/terminal/log/WS)       │
 │    ├── DashboardServer (Flask+SocketIO :9876)        │
 │    └── TUI (Rich terminal dashboard)                │
 │                                                     │
 │  ┌────────── Docker (isolated network) ───────────┐ │
 │  │  OpenClaw Container (hardened)                  │ │
 │  │  Port 127.0.0.1:18789 → Gateway UI             │ │
 │  └─────────────────────────────────────────────────┘ │
 └─────────────────────────────────────────────────────┘
```

---

## Documentation

- **[Getting Started](docs/getting-started.md)** — Installation, first run, configuration
- **[Security Model](docs/security.md)** — Deep dive into all 12 hardening layers
- **[Monitoring Guide](docs/monitoring.md)** — Understanding alerts, thresholds, auto-pause
- **[Dashboard Guide](docs/dashboard.md)** — Web dashboard features and usage
- **[Development](docs/development.md)** — Setting up a dev environment, running tests
- **[Contributing](CONTRIBUTING.md)** — How to contribute to CrabPot

---

## Requirements

- **Linux** or **WSL2** (Windows Subsystem for Linux 2)
- **Docker** with Docker Compose plugin
- **Python 3.9+**

---

## License

MIT License. See [LICENSE](LICENSE) for details.
